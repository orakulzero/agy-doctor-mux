import os
import tempfile
from pathlib import Path
from agy_doctor_mux.desktop_doctor import diagnose_desktop_and_sandbox_health

def test_diagnose_desktop_and_sandbox_health_with_file_working_dir():
    with tempfile.NamedTemporaryFile() as tmp_file:
        tmp_path = Path(tmp_file.name)
        
        # Call the function with working_dir pointing to a regular file
        result = diagnose_desktop_and_sandbox_health(working_dir=tmp_path)
        
        sandbox_info = result["sandbox"]
        
        # Verify sandbox_writeable equals temp_writeable
        assert sandbox_info["sandbox_writeable"] == sandbox_info["temp_writeable"]
        
        # Verify no _agy_wdir_probe_* file was created in the parent directory
        # The function creates probe files using os.getpid()
        probe_files = list(tmp_path.parent.glob(f"_agy_wdir_probe_{os.getpid()}.tmp"))
        assert len(probe_files) == 0

        # Verify no _agy_wdir_probe_* file was created matching the temporary file's name either
        # (just in case it tried to append to it like a string)
        probe_files_str = list(tmp_path.parent.glob(f"{tmp_path.name}_agy_wdir_probe_*.tmp"))
        assert len(probe_files_str) == 0

        # Verify sandbox_info is a coherent dict
        assert isinstance(sandbox_info, dict)
        assert "write_access" in sandbox_info
        assert "isolation_type" in sandbox_info
        assert "is_sandboxed" in sandbox_info
        assert "container_markers" in sandbox_info
        assert "loopback_binding" in sandbox_info
        assert "loopback_available" in sandbox_info
        assert "network" in sandbox_info
        assert isinstance(sandbox_info["network"], dict)
        assert "bind_host" in sandbox_info["network"]
