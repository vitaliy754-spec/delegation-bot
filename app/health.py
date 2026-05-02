from aiohttp import web

async def health(_): return web.Response(text="ok")

def make_app():
    app = web.Application()
    app.router.add_get("/health", health)
    return app
