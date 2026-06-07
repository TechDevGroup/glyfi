"""cli -- the argparse entrypoint: ``glyfi --base-url URL [--session S] [--list]``.

HTTP-only: point it at a running server. ``--list`` GETs the server-exposed routable subjects and exits (a
discovery aid, no app launched). Otherwise it resolves the NAMED ``GLYFI_*`` config, builds the MVVM ViewModel
over the HTTP transport, and runs the curses app.
"""
import argparse
import sys


def main(argv=None) -> None:
    """``glyfi --base-url URL [--session S] [--list]`` -- the MVVM curses app (tmux-able)."""
    parser = argparse.ArgumentParser(description='glyfi -- an extensible, configurable curses TUI (HTTP-only)')
    parser.add_argument('--base-url', metavar='BASE_URL', default=None,
                        help='the running server URL (e.g. http://127.0.0.1:8800); defaults to GLYFI_BASE_URL')
    parser.add_argument('--session', default='glyfi-1', help='the session id to run over')
    parser.add_argument('--list', action='store_true',
                        help="GET the server-exposed routable subjects and exit (discover, don't launch)")
    args = parser.parse_args(argv)

    from glyfi.config import load_config
    cfg = load_config()
    base_url = args.base_url or cfg.base_url

    if args.list:
        from glyfi.transport import HttpTransport
        for s in HttpTransport(base_url).list_subjects():
            sys.stdout.write(f"{s['subject']}  (label {s['label']!r})\n")
        return

    from glyfi.app import build_viewmodel, run
    from glyfi.ui.settings import AppSettings
    viewmodel = build_viewmodel(base_url=base_url, session_id=args.session,
                                settings=AppSettings(title=cfg.title), modes=cfg.modes)
    run(viewmodel)


if __name__ == '__main__':
    main()
