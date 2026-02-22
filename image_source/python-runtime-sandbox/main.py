# Copyright 2025 The Kubernetes Authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import subprocess
import os
import logging
import urllib.parse

from fastapi import FastAPI, UploadFile, File
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

WORKSPACE_DIR = os.path.realpath(os.getenv("WORKSPACE_DIR", "/tmp/workspace"))
RUNTIME_DIR = os.path.realpath(os.getenv("XDG_RUNTIME_DIR", "/tmp/runtime"))
CACHE_DIR = os.path.realpath(os.getenv("XDG_CACHE_HOME", os.path.join(WORKSPACE_DIR, ".cache")))
CONFIG_DIR = os.path.realpath(os.getenv("XDG_CONFIG_HOME", os.path.join(WORKSPACE_DIR, ".config")))

class ExecuteRequest(BaseModel):
    """Request model for the /execute endpoint."""
    command: str

class ExecuteResponse(BaseModel):
    """Response model for the /execute endpoint."""
    stdout: str
    stderr: str
    exit_code: int

def get_safe_path(file_path: str) -> str:
    """Sanitizes the file path to ensure it stays within the workspace."""
    base_dir = WORKSPACE_DIR
    # Remove leading slashes to ensure path is relative
    clean_path = file_path.lstrip("/")
    full_path = os.path.realpath(os.path.join(base_dir, clean_path))

    if os.path.commonpath([base_dir, full_path]) != base_dir:
        raise ValueError("Access denied: Path must be within the workspace")
    
    return full_path

app = FastAPI(
    title="Agentic Sandbox Runtime",
    description="An API server for executing commands and managing files in a secure sandbox.",
    version="1.0.0",
)

@app.get("/", summary="Health Check")
async def health_check():
    """A simple health check endpoint to confirm the server is running."""
    return {"status": "ok", "message": "Sandbox Runtime is active."}


@app.on_event("startup")
async def ensure_workspace():
    """Ensure the command/file workspace exists and is writable."""
    os.makedirs(WORKSPACE_DIR, exist_ok=True)
    os.makedirs(RUNTIME_DIR, exist_ok=True)
    os.makedirs(CACHE_DIR, exist_ok=True)
    os.makedirs(CONFIG_DIR, exist_ok=True)

@app.post("/execute", summary="Execute a shell command", response_model=ExecuteResponse)
async def execute_command(request: ExecuteRequest):
    """
    Executes a shell command inside the sandbox and returns its output.
    Runs the full command string in a shell.
    """
    try:
        cmd_env = os.environ.copy()
        cmd_env.update(
            {
                "HOME": WORKSPACE_DIR,
                "XDG_RUNTIME_DIR": RUNTIME_DIR,
                "XDG_CACHE_HOME": CACHE_DIR,
                "XDG_CONFIG_HOME": CONFIG_DIR,
            }
        )

        # Execute the command from the isolated workspace directory.
        process = subprocess.run(
            request.command,
            capture_output=True,
            text=True,
            cwd=WORKSPACE_DIR,
            env=cmd_env,
            shell=True,
        )
        return ExecuteResponse(
            stdout=process.stdout,
            stderr=process.stderr,
            exit_code=process.returncode
        )
    except Exception as e:
        return ExecuteResponse(
            stdout="",
            stderr=f"Failed to execute command: {str(e)}",
            exit_code=1
        )

@app.post("/upload", summary="Upload a file to the sandbox")
async def upload_file(file: UploadFile = File(...)):
    """
    Receives a file and saves it to the workspace directory in the sandbox.
    """
    try:
        logging.info(f"--- UPLOAD_FILE CALLED: Attempting to save '{file.filename}' ---")
        file_path = get_safe_path(file.filename)
        
        with open(file_path, "wb") as f:
            f.write(await file.read())
            
        return JSONResponse(
            status_code=200,
            content={"message": f"File '{file.filename}' uploaded successfully."}
        )
    except Exception as e:
        logging.exception("An error occurred during file upload.") 
        return JSONResponse(
            status_code=500,
            content={"message": f"File upload failed: {str(e)}"}
        )

@app.get("/download/{encoded_file_path:path}", summary="Download a file from the sandbox")
async def download_file(encoded_file_path: str):
    """
    Downloads a specified file from the workspace directory in the sandbox.
    """
    decoded_path = urllib.parse.unquote(encoded_file_path)
    try:
        full_path = get_safe_path(decoded_path)
    except ValueError:
        return JSONResponse(status_code=403, content={"message": "Access denied"})

    if os.path.isfile(full_path):
        return FileResponse(path=full_path, media_type='application/octet-stream', filename=decoded_path)
    return JSONResponse(status_code=404, content={"message": "File not found"})

@app.get("/list/{encoded_file_path:path}", summary="List files in a directory")
async def list_files(encoded_file_path: str):
    """
    Lists the contents of a directory under the workspace directory in the sandbox.
    """
    decoded_path = urllib.parse.unquote(encoded_file_path)
    try:
        full_path = get_safe_path(decoded_path)
    except ValueError:
        return JSONResponse(status_code=403, content={"message": "Access denied"})

    if not os.path.isdir(full_path):
        return JSONResponse(status_code=404, content={"message": "Path is not a directory"})
    
    try:
        entries = []
        with os.scandir(full_path) as it:
            for entry in it:
                stats = entry.stat()
                entries.append({
                    "name": entry.name,
                    "size": stats.st_size,
                    "type": "directory" if entry.is_dir() else "file",
                    "mod_time": stats.st_mtime
                })
        return JSONResponse(status_code=200, content=entries)
    except Exception as e:
        return JSONResponse(status_code=500, content={"message": f"List files failed: {str(e)}"})

@app.get("/exists/{encoded_file_path:path}", summary="Check if the relative path exists")
async def exists(encoded_file_path: str):
    """
    Checks if a specified file or directory exists under the workspace directory in the sandbox.
    """
    decoded_path = urllib.parse.unquote(encoded_file_path)
    try:
        full_path = get_safe_path(decoded_path)
    except ValueError:
        return JSONResponse(status_code=403, content={"message": "Access denied"})

    return JSONResponse(status_code=200, content={
        "path": decoded_path,
        "exists": os.path.exists(full_path)
    })
