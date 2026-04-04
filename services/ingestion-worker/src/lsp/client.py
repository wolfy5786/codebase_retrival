"""
Shared LSP client: language-agnostic JSON-RPC over stdio.
Accepts a pre-started subprocess.Popen process and communicates via Content-Length framed JSON-RPC.
"""
import json
import logging
import subprocess
from typing import Any

from lsprotocol.types import (
    ClientCapabilities,
    DocumentSymbol,
    InitializedParams,
    InitializeParams,
    TextDocumentIdentifier,
    TextDocumentItem,
)
from lsprotocol.types import (
    DidOpenTextDocumentParams,
    DocumentSymbolParams,
)

logger = logging.getLogger(__name__)


class LspClient:
    """
    Language-agnostic LSP client that communicates over stdio via JSON-RPC.
    """

    def __init__(self, process: subprocess.Popen, workspace_root: str):
        """
        Args:
            process: Running LSP server process with stdin/stdout pipes
            workspace_root: Workspace root URI for initialize
        """
        self.process = process
        self.workspace_root = workspace_root
        self._msg_id = 0
        self._initialized = False

    def _next_id(self) -> int:
        """Generate next message ID."""
        self._msg_id += 1
        return self._msg_id

    def _read_message(self) -> dict | None:
        """
        Read a single JSON-RPC message from the LSP server.
        Returns None on EOF or parse error.
        """
        try:
            # Read headers until blank line
            headers = {}
            while True:
                line = self.process.stdout.readline()
                if not line:
                    return None
                line = line.strip()
                if not line:
                    break
                if b":" in line:
                    key, value = line.split(b":", 1)
                    headers[key.strip().lower()] = value.strip()

            content_length = int(headers.get(b"content-length", 0))
            if content_length == 0:
                return None

            # Read content
            content = self.process.stdout.read(content_length)
            return json.loads(content.decode("utf-8"))

        except Exception as e:
            logger.debug("LSP read_message error: %s", e)
            return None

    def _write_message(self, message: dict) -> None:
        """Write a JSON-RPC message to the LSP server."""
        try:
            content = json.dumps(message, ensure_ascii=False).encode("utf-8")
            header = f"Content-Length: {len(content)}\r\n\r\n".encode("utf-8")
            self.process.stdin.write(header)
            self.process.stdin.write(content)
            self.process.stdin.flush()
        except Exception as e:
            logger.exception("LSP write_message error: %s", e)
            raise

    def _send_request(self, method: str, params: Any) -> dict:
        """Send a JSON-RPC request and wait for response."""
        msg_id = self._next_id()
        request = {
            "jsonrpc": "2.0",
            "id": msg_id,
            "method": method,
            "params": params,
        }
        logger.debug("LSP request: %s", method)
        self._write_message(request)

        # Read responses until we get our ID back
        while True:
            response = self._read_message()
            if response is None:
                raise RuntimeError(f"LSP server closed before responding to {method}")
            if response.get("id") == msg_id:
                if "error" in response:
                    raise RuntimeError(f"LSP error in {method}: {response['error']}")
                return response.get("result", {})
            # Skip notifications or other responses

    def _send_notification(self, method: str, params: Any) -> None:
        """Send a JSON-RPC notification (no response expected)."""
        notification = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        }
        logger.debug("LSP notification: %s", method)
        self._write_message(notification)

    def initialize(self, initialization_options: dict | None = None) -> dict:
        """
        Send initialize request to LSP server.
        Returns the initialize result.
        """
        params = {
            "processId": None,
            "rootUri": f"file://{self.workspace_root}",
            "capabilities": {
                "textDocument": {
                    "synchronization": {"dynamicRegistration": False},
                    "documentSymbol": {"dynamicRegistration": False, "hierarchicalDocumentSymbolSupport": True},
                    "hover": {"dynamicRegistration": False, "contentFormat": ["markdown", "plaintext"]},
                },
            },
        }
        if initialization_options:
            params["initializationOptions"] = initialization_options

        result = self._send_request("initialize", params)
        self._send_notification("initialized", {})
        self._initialized = True
        logger.info("LSP initialized for workspace: %s", self.workspace_root)
        return result

    def did_open(self, file_path: str, language_id: str, content: str) -> None:
        """
        Send textDocument/didOpen notification.
        """
        params = {
            "textDocument": {
                "uri": f"file://{file_path}",
                "languageId": language_id,
                "version": 1,
                "text": content,
            }
        }
        self._send_notification("textDocument/didOpen", params)

    def document_symbol(self, file_path: str) -> list[dict]:
        """
        Request textDocument/documentSymbol.
        Returns a list of DocumentSymbol dicts (hierarchical).
        """
        params = {
            "textDocument": {
                "uri": f"file://{file_path}",
            }
        }
        result = self._send_request("textDocument/documentSymbol", params)
        if not result:
            return []
        return result

    def hover(self, file_path: str, line: int, character: int) -> dict | None:
        """
        Request textDocument/hover at 0-based line/character (LSP Position).
        Returns the hover result dict, or None if the server returns null.
        """
        params = {
            "textDocument": {
                "uri": f"file://{file_path}",
            },
            "position": {"line": line, "character": character},
        }
        result = self._send_request("textDocument/hover", params)
        return result if result else None

    def shutdown(self) -> None:
        """Gracefully shutdown the LSP server."""
        try:
            if self._initialized:
                self._send_request("shutdown", {})
                self._send_notification("exit", {})
                logger.info("LSP shutdown sent")
        except Exception as e:
            logger.debug("LSP shutdown error (expected if server already dead): %s", e)

    def close(self) -> None:
        """Close the LSP client and terminate the server process."""
        try:
            self.shutdown()
        finally:
            try:
                self.process.terminate()
                self.process.wait(timeout=5)
            except Exception as e:
                logger.debug("LSP process termination error: %s", e)
                try:
                    self.process.kill()
                except Exception:
                    pass
