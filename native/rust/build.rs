use pyo3_build_config::use_pyo3_cfgs;

fn main() {
    // pyo3-build-config automatically extracts the Python version and
    // linkings settings from the sysconfig data. It then persists these
    // as cfgs so that pyo3 can configure itself appropriately at compile time.
    //
    // To see the full config call `python -c "import sysconfig; print(sysconfig.get_config_dict())"`
    use_pyo3_cfgs();
}
