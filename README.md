# luzxfer

Intercepting proxy and web pentesting workbench that lives in your terminal.

Built around the [OWASP WSTG](https://owasp.org/www-project-web-security-testing-guide/)
rather than around requests: it tracks which tests you have run against which
endpoints, ties findings to the traffic that proves them, and keeps that state
across sessions.

> **Status: alpha.** The core, named sessions, the history and the repeater
> work. Intruder, sitemap, scope and the WSTG coverage matrix are not built
> yet. See the roadmap.

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

Not on PyPI yet. From source:

```bash
git clone https://github.com/xXJuanDavidXx/Luzxfer
cd luzxfer
pip install -e .
```

Python 3.10+. The only runtime dependency is [Textual](https://textual.textualize.io/).
Everything else is the standard library, deliberately: that is what keeps it
installable on Termux, where there are no prebuilt wheels and any C or Rust
extension is compiled on the phone.

Two optional extras, both of which compile and therefore neither of which
works on Termux — that is why they are extras and not dependencies:

```bash
pip install -e '.[mitm]'   # HTTPS interception
pip install -e '.[br]'     # read brotli bodies (see Compression)
```

## Use

```bash
luzxfer                              # resumes your last session, proxy on :8080
luzxfer -s acme-corp                 # open or create a named session
luzxfer --sesiones                   # list what is saved, then exit
luzxfer -p 9090                      # another port
luzxfer -u http://127.0.0.1:8099     # reverse mode, for a local lab
luzxfer -s acme-corp --no-engine     # review a session without starting the proxy
luzxfer -d ~/work/target.db          # a session file at a path you choose
luzxfer -d :memory:                  # throwaway, lost on exit
```

### Sessions

**Closing luzxfer does not lose your history.** Sessions live in
`~/.local/share/luzxfer/sesiones/` (or under `$XDG_DATA_HOME`), one SQLite
file each, holding the traffic, the candidates, your notes and your marks.
Running with no arguments reopens the last one you used.

`s` opens the session picker: what is saved, how much is in each, which one
is open. It reads read-only, so looking does not touch anything. It will not
delete the session you have open — the `Store` would keep writing to a file
that is gone and you would lose the day's work.

Session names are checked against a whitelist (letters, digits, `.`, `_`,
`-`, starting alphanumeric, 64 max). The name becomes a filename, and a tool
that forwards arbitrary requests has no business also writing arbitrary
paths.

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
| `t` | toggle request+response side by side, and back |
| `n` | write a note on the selected flow |
| `m` | mark a flow |
| `v` | confirm the selected candidate as a real finding |
| `s` | sessions |
| `c` | clear the history (findings are kept) |
| `g` / `G` | first / last flow |
| `q` | quit |

`t` and the button next to the filter do the same thing: request and
response in two columns instead of two tabs, the way Burp lets you lay them
out. The candidates tab stays reachable either way, and the choice is
remembered with the session.

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

You confirm, with `v`. That is the line between a candidate and a finding,
and nothing but a human crosses it.

## What the proxy rewrites

Two headers, both on by default, both for the same reason: without them
bodies arrive that cannot be read, and **a body the detector cannot read is
a detector that finds nothing and does not say why.** Each has its own
switch, because the reasons to want them back are independent.

### Cache validators

A browser that already has the page sends `If-None-Match` or
`If-Modified-Since`, the server answers `304 Not Modified`, and the body is
empty. On a real target this happens on every reload, so a great deal of
your history ends up as 304s with nothing in them — and the detector scores
zero on all of it.

So the proxy drops those two headers. Measured against OWASP Juice Shop:

```
with the validator:     304 Not Modified      0 bytes    0 candidates
validator dropped:      200 OK             9984 bytes    1 candidate
```

`--conservar-cache` keeps them, which is what you want when cache poisoning
or cache deception is the thing you are testing — there those headers are
the experiment, not an obstacle.

**The proxy does not follow redirects, and that is deliberate.** A `30x` is
shown exactly as the server sent it; following it would hide the response
you came to look at. The browser follows them, as it would anyway.

### Compression

The detector reads the *decoded* body, because searching for a reflection in
gzip bytes finds nothing. gzip and deflate are standard library. Brotli is
not — and brotli is what nginx, Cloudflare and Express' compression
middleware reach for by default, so on a modern target this is the common
case, not an edge one.

So the proxy trims `br` (and anything else it cannot undo) out of the
client's `Accept-Encoding` before forwarding. It trims rather than replaces,
keeping the order and the `q=` values the client sent. Without this the
detector goes quietly blind: it searches compressed bytes, finds nothing,
and reports nothing — a false negative that leaves no trace.

`--conservar-encoding` turns the trimming off, for when how the server
responds to each encoding is the thing you are testing. `pip install
'.[br]'` decodes brotli properly instead. If a body still arrives in
something unreadable, the response pane says so and says the detector could
not read it either, rather than showing you binary and keeping quiet.

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
- [x] Named sessions, persistent by default, with a picker
- [x] Notes, confirmed findings, side-by-side request/response
- [ ] Intruder, four modes, with grep-match on results
- [ ] Sitemap tree and scope
- [ ] Intercept and edit in flight — the real gap against Burp today
- [ ] DAST, on a leash: scope required, fired by hand, rate limited
- [ ] WSTG coverage matrix and report generation
- [ ] mitmproxy engine adapter
- [ ] Plugin API

`docs/direccion.md` has the reasoning behind that order, and why AI is
deferred rather than planned.

## Contributing

Issues and pull requests welcome. The design rule worth knowing before you
start: **no interface talks to an engine directly, and nothing in `core/`
imports from `tui/`.** That separation is what keeps a second front end, or a
headless run, possible.

## License

Apache-2.0. See [LICENSE](LICENSE).
