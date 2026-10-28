"""Serve only built frontend files; API and missing assets never get HTML."""
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse


def mount_frontend(app: FastAPI, directory: Path):
    root = directory.resolve()

    @app.get("/{path:path}", include_in_schema=False)
    async def frontend(path: str):
        if path == "api" or path.startswith("api/"):
            return JSONResponse({"error": "Ressource API introuvable."}, status_code=404)
        if "\\" in path or "\x00" in path or any(part.startswith(".") for part in path.split("/")):
            return JSONResponse({"error": "Fichier introuvable."}, status_code=404)
        candidate = (root / path).resolve()
        if not candidate.is_relative_to(root):
            return JSONResponse({"error": "Fichier introuvable."}, status_code=404)
        if candidate.is_file():
            return FileResponse(candidate)
        if path.startswith("assets/") or Path(path).suffix:
            return JSONResponse({"error": "Fichier introuvable."}, status_code=404)
        index = root / "index.html"
        if index.is_file():
            return FileResponse(index)
        return JSONResponse({"error": "Interface non compilée. Exécutez npm run build."}, status_code=503)
