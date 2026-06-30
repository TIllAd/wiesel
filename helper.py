docker compose exec wiesel-backend python -c "
import asyncio
from backend.main import analytics_month_files
print(asyncio.run(analytics_month_files(None)))
"