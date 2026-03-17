"""
Java LSP server adapter: spawns jdtls (Eclipse JDT Language Server).
"""
import logging
import os
import platform
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


def start_jdtls(workspace_root: str) -> subprocess.Popen:
    """
    Start jdtls (Eclipse JDT Language Server) for Java.
    
    Args:
        workspace_root: Workspace directory path for jdtls
        
    Returns:
        Running subprocess.Popen with stdin/stdout pipes
    """
    jdtls_home = os.environ.get("JDTLS_HOME")
    if not jdtls_home:
        logger.warning(
            "JDTLS_HOME not set in environment (os.environ.get returned %r), using fallback path",
            jdtls_home,
        )
        # Fallback: relative to project root
        jdtls_home = Path(__file__).parent.parent.parent.parent.parent.parent / "infrastructure" / "LSP" / "jdtls"
        jdtls_home = str(jdtls_home.resolve())
    
    logger.info("jdtls_home=%s", jdtls_home)
    jdtls_data_dir = os.environ.get("JDTLS_DATA_DIR", "/tmp/jdtls-workspace")
    
    # Determine jdtls script based on platform
    if platform.system() == "Windows":
        jdtls_script = Path(jdtls_home) / "bin" / "jdtls.bat"
    else:
        jdtls_script = Path(jdtls_home) / "bin" / "jdtls"
    
    if not jdtls_script.exists():
        logger.warning(
            "jdtls not found at %s. Set JDTLS_HOME env var or install jdtls at infrastructure/LSP/jdtls",
            jdtls_script,
        )
        raise FileNotFoundError(
            f"jdtls not found at {jdtls_script}. Set JDTLS_HOME env var or install jdtls at infrastructure/LSP/jdtls"
        )
    
    # Create workspace data directory if it doesn't exist
    workspace_data = Path(jdtls_data_dir) / "data"
    workspace_data.mkdir(parents=True, exist_ok=True)
    
    # Spawn jdtls
    cmd = [
        str(jdtls_script),
        "-data", str(workspace_data),
    ]
    
    logger.info("Starting jdtls: %s", " ".join(cmd))
    
    try:
        process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=workspace_root,
        )
        logger.info("jdtls started with PID %s", process.pid)
        return process
    except Exception as e:
        logger.exception("Failed to start jdtls: %s", e)
        raise


def get_initialization_options(workspace_root: str) -> dict:
    """
    Get jdtls-specific initialization options.
    
    Args:
        workspace_root: Workspace directory path
        
    Returns:
        initializationOptions dict for jdtls
    """
    jdtls_data_dir = os.environ.get("JDTLS_DATA_DIR", "/tmp/jdtls-workspace")
    
    return {
        "workspaceFolders": [f"file://{workspace_root}"],
        "settings": {
            "java": {
                "home": os.environ.get("JAVA_HOME", ""),
                "configuration": {
                    "runtimes": []
                },
                "format": {
                    "enabled": False
                }
            }
        },
        "extendedClientCapabilities": {
            "classFileContentsSupport": False
        }
    }
