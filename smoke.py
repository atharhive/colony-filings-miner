
import sys, json
sys.path.insert(0, ".")
from pathlib import Path
from src.service import FilingsService
svc = FilingsService(Path(".cache"))
for entity, period in [("Apple Inc.", "last 12 months"), ("Maersk", "2024"), ("Tesla", "last 6 months")]:
    a = svc.answer(entity, period)
    print(json.dumps({"q": f"{entity} / {period}", "status": a.status, "count": a.filing_count,
                      "source": a.source, "window": a.window, "note": a.note,
                      "first": a.filings[0] if a.filings else None}, indent=1))
