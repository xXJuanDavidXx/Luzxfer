# luzxfer

Intercepting proxy and web pentesting workbench that lives in your terminal.

Built around the [OWASP WSTG](https://owasp.org/www-project-web-security-testing-guide/)
rather than around requests: it tracks which tests you have run against which
endpoints, ties findings to the traffic that proves them, and keeps that state
across sessions.

> **Status: alpha.** The core, the history and the repeater work. Intruder,
> sitemap and the WSTG coverage matrix are not built yet. See the roadmap.

---

## Why another one

Burp is excellent and this does not try to replace it. It exists because of
three gaps:

- **It runs where Burp cannot.** A terminal app with no native dependencies
  works over SSH and on Android under Termux, where no JVM tool will.
- **It is organised by methodology, not by tool.** Burp knows your requests;
  it does not know which WSTG tests you still owe the client. That bookkeeping
  usually ends up in a separate spreadsheet.
- **Evidence is attached to findings.** A finding stores the exact flows that
  prove it, so the PoC does not get rebuilt by hand at report time.

## Install

```bash
pip install luzxfer
```

Python 3.10+. The only runtime dependency is [Textual](https://textual.textualize.io/).
Everything else is the standard library, deliberately: that is what keeps it
installable on Termux, where there are no prebuilt wheels and any C or Rust
extension is compiled on the phone.

For HTTPS interception you also need the mitmproxy engine:

```bash
pip install 'luzxfer[mitm]'
```

## Use

```bash
luzxfer                                  # proxy on 127.0.0.1:8080
luzxfer -p 9090                          # another port
luzxfer -u http://127.0.0.1:8099         # reverse mode, for a local lab
luzxfer -d ~/work/target.db              # persist the session
luzxfer --no-engine -d ~/work/target.db  # review a saved session
```

**Reverse mode matters more than it looks.** Chromium-based browsers never send
`localhost` or `127.0.0.1` through a configured proxy — it is an implicit bypass
rule, for security reasons. So to watch traffic against a local lab you point
the browser at the proxy's own port and let it forward upstream, instead of
configuring a system proxy that would be ignored.

### Keys

| key | does |
| --- | --- |
| `j` / `k` or arrows | move through the history |
| `f` | focus the filter |
| `r` | open the repeater on the selected flow |
| `m` | mark a flow |
| `c` | clear the history (findings are kept) |
| `g` / `G` | first / last flow |
| `q` | quit |

Inside the repeater: `ctrl+s` sends, `esc` closes. `Content-Length` is
recalculated on send, because editing a raw request by hand and forgetting it
is the most common mistake there is.

**What you write is what travels.** The repeater writes to a raw socket instead
of going through an HTTP library, so duplicate headers stay duplicated, no
header is added behind your back, and non-standard methods go out as typed.
A repeater that tidies up your request is useless for testing what the server
does with the untidy one. It also speaks TLS on its own, so it can hit HTTPS
targets even though the built-in proxy engine does not intercept them.
Sending happens off the UI thread: a slow target never freezes the interface.

## Candidates, not findings

While you browse, luzxfer flags things worth a look: reflected input, cookies
missing `HttpOnly` / `Secure` / `SameSite`, absent security headers, version
leaks, server errors. Each one carries the WSTG IDs it maps to.

**It is not a scanner and it confirms nothing.** A reflection may be perfectly
escaped in the context where it lands. Server-wide issues are recorded once per
host, not once per URL — repeating the same finding on every path is the noise
that makes scanner output useless.

## Engines

The core never talks to a proxy directly. It talks to an engine interface, so
swapping engines is swapping a class.

| engine | TLS | HTTP/2 | WebSockets | needs |
| --- | --- | --- | --- | --- |
| `builtin` (default) | no | no | no | nothing, stdlib only |
| `mitmproxy` | yes | yes | yes | `pip install 'luzxfer[mitm]'` |

The built-in engine answers `CONNECT` with a 501 that says why, instead of
failing silently. Intercepting TLS needs a local CA and per-host certificate
generation, which is exactly the heavy dependency the built-in engine avoids.

## Security

This tool forwards arbitrary requests. **Keep it on loopback.** Binding it to a
routable interface hands anyone on your network an open proxy. If you need to
reach it from another machine, tunnel over SSH.

## Roadmap

- [x] Core, SQLite store, engine interface
- [x] Built-in HTTP engine (forward and reverse)
- [x] History with filters, detail panes, candidates
- [x] Repeater
- [ ] Intruder, four modes, with grep-match on results
- [ ] Sitemap tree and scope
- [ ] WSTG coverage matrix and report generation
- [ ] mitmproxy engine adapter
- [ ] Plugin API

## Contributing

Issues and pull requests welcome. The design rule worth knowing before you
start: **no interface talks to an engine directly, and nothing in `core/`
imports from `tui/`.** That separation is what keeps a second front end, or a
headless run, possible.

## License

Apache-2.0. See [LICENSE](LICENSE).
