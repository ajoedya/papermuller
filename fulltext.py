"""Acquire public open-access PDFs selected by OpenAlex, with explicit fallback."""
import ipaddress
import http.client
import socket
import urllib.error
import urllib.parse
import urllib.request

import sources

# Some managed environments delegate DNS to their HTTPS proxy. Only these known
# public publishing services may use proxy-side DNS when local resolution fails.
PROXY_DNS_DOMAINS = ('journals.plos.org', 'arxiv.org', 'export.arxiv.org',
                     'pmc.ncbi.nlm.nih.gov', 'europepmc.org')


def validate_url(url):
    parsed = urllib.parse.urlsplit(url)
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password
            or parsed.port not in (None, 443) or len(url) > 4096):
        raise ValueError('Only public HTTPS PDF URLs without credentials are allowed.')
    host = parsed.hostname.lower().rstrip('.')
    # Reject private literals and local names before considering proxy DNS.
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if (literal is not None and not literal.is_global) or host in ('localhost', 'metadata.google.internal') or host.endswith(('.local', '.internal', '.localhost')):
        raise ValueError('PDF destination is not a public Internet address.')
    try:
        addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except socket.gaierror:
        proxy = urllib.request.getproxies().get('https')
        if proxy and host in PROXY_DNS_DOMAINS:
            return url  # HTTPS CONNECT and TLS validation remain handled by urllib.
        raise ValueError('Public DNS resolution is unavailable for this PDF host.')
    if not addresses or any(not ipaddress.ip_address(a[4][0].split('%')[0]).is_global for a in addresses):
        raise ValueError('PDF destination is not a public Internet address.')
    return url


class PublicRedirects(urllib.request.HTTPRedirectHandler):
    max_redirections = 4
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def public_connection(address, timeout=socket._GLOBAL_DEFAULT_TIMEOUT, source_address=None):
    """Pin direct connections to a validated numeric address, avoiding DNS rebinding."""
    host, port = address
    addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(a[4][0].split('%')[0]).is_global for a in addresses):
        raise ValueError('PDF connection destination is not public.')
    last_error = None
    for address in addresses:
        try:
            return socket.create_connection((address[4][0], port), timeout, source_address)
        except OSError as exc:
            last_error = exc
    raise last_error


class PublicHTTPSConnection(http.client.HTTPSConnection):
    def connect(self):
        # Configured proxies resolve CONNECT destinations themselves. Keep that
        # supported route; only direct origin connections need numeric pinning.
        if not self._tunnel_host:
            self._create_connection = public_connection
        return super().connect()


class PublicHTTPSHandler(urllib.request.HTTPSHandler):
    def https_open(self, request):
        return self.do_open(PublicHTTPSConnection, request,
                            context=self._context)


def download_pdf(url):
    validate_url(url)
    opener = urllib.request.build_opener(PublicRedirects(), PublicHTTPSHandler())
    request = urllib.request.Request(url, headers={'User-Agent': 'Papermuller/1.0', 'Accept': 'application/pdf'})
    with opener.open(request, timeout=30) as response:
        validate_url(response.geturl())
        # Stream with a hard limit even when length is missing or incorrect.
        content = response.read(sources.MAX_PDF_BYTES + 1)
    if len(content) > sources.MAX_PDF_BYTES:
        raise ValueError('Open-access PDF exceeds the 12 MB limit.')
    if not content.startswith(b'%PDF-'):
        raise ValueError('The source returned a web page or non-PDF response.')
    return content


def acquire(paper, settings):
    """Prefer uploaded/cached text; otherwise try at most three OA PDF locations."""
    source = sources.source_for_paper(paper, settings)
    if source['source_type'] == 'full_text_pdf':
        return source, {'status': 'available', 'origin': source.get('origin', 'uploaded'), 'url': source.get('source_url', '')}
    if settings.get('DEMO_MODE'):
        return source, {'status': 'abstract_only', 'reason': 'Offline demo: no network downloads.'}
    if not settings.get('FETCH_FULLTEXT', True):
        return source, {'status': 'abstract_only', 'reason': 'Automatic full-text retrieval is disabled.'}
    urls = paper.get('oa_pdf_urls') or []
    errors = []
    for url in urls[:3]:
        try:
            content = download_pdf(url)
            sources.import_pdf(sources.library_path(settings), paper['doi'], paper['id'] + '.pdf', content,
                               expected_paper=paper, source_url=url, origin='open_access')
            return sources.source_for_paper(paper, settings), {'status': 'available', 'origin': 'open_access', 'url': url}
        except urllib.error.HTTPError as exc:
            errors.append(f'Publisher returned HTTP {exc.code}.')
        except (ValueError, OSError, RuntimeError, urllib.error.URLError) as exc:
            # Do not leak signed URLs, credentials, or proxy diagnostics into exports.
            errors.append(str(exc) if isinstance(exc, ValueError) else 'PDF download or extraction unavailable.')
    return source, {'status': 'abstract_only', 'reason': '; '.join(errors) or 'No public open-access PDF URL was supplied by OpenAlex.'}
