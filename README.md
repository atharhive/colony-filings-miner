# colony-filings-miner

A Telegraph miner for `REGULATORY_FILING_MONITOR_GENERAL`: count an issuer's SEC filings
inside a stated window, and say "unresolved" rather than guessing.

Built for [Colony](https://github.com/atharhive/colony), which buys this intent as one of
its seven claims, but it is a general provider: any app that needs a filing count can call
it.

## The one rule

**Zero and unresolved are different answers.** A company with no filings in the window is
`filing_count: 0` and `ok`. A company the SEC has never heard of, or an upstream that did
not answer, is `unresolved` with the count left at zero and the reason in `X-Miner-Status`
and the note. A miner that collapses those two into "0" quietly poisons every decision
that trusts the count.

## Sources

All keyless, all public SEC endpoints:

| Endpoint | Use |
|---|---|
| `www.sec.gov/files/company_tickers.json` | CIK lookup, cached 24h |
| `data.sec.gov/submissions/CIK##########.json` | that issuer's filing index |
| `efts.sec.gov/LATEST/search-index` | full-text fallback, reported but never counted |

Full-text hits are mentions inside *other* companies' filings. Maersk does not file with
the SEC, and "156 mentions" is not "156 Maersk filings", so the miner returns unresolved
and says how many mentions it saw.

## Periods accepted

`last 12 months`, `past 90 days`, `last 3 years`, `2025`, `FY2025`, `since 2024-01-01`,
`2024-01-01 to 2024-12-31`. Anything else is unresolved: a guessed window produces a
confident count for the wrong dates, which is worse than no answer.

## Run

```bash
python3 -m src.server --host 0.0.0.0 --port 8099
```

```bash
curl -s localhost:8099/filings -H 'content-type: application/json' \
  -d '{"entity":"Apple Inc.","period":"last 12 months"}' | jq '{entity, filing_count}'
```

## Test

```bash
pytest tests -q      # 23 tests, no network
```

The tests that matter: a real zero stays `ok`; a failed upstream is `unresolved`;
the count is not capped by the listing limit; an unparseable period asks nothing.

## Register on Telegraph

`miner/colony-filings.yaml` is the registration document. It needs a live `base_url`
before it is registered, and a MACHINA bond on Ethereum Sepolia ($1 plus $0.10 per extra
intent). Registration is a one-shot on-chain call; after an update the miner sits offline
until the new YAML validates, so the YAML is changed rarely and pinned to a commit.

## Design notes

`docs/DECISIONS.md` explains the two calls that shaped this: why the count is never
capped, and why full-text mentions are reported but not counted.

MIT.
