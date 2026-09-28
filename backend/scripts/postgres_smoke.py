import asyncio
import os

import asyncpg


async def main() -> None:
    conn = await asyncpg.connect(os.environ["POSTGRES_TEST_URL"])
    assert await conn.fetchval("SELECT 1") == 1
    await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
