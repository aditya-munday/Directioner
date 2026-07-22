//! Shared memory implementation for cross-process communication.
//!
//! This module provides a simplified shared memory interface that can be used
//! for communication between Python and Rust components.

use memmap2::{MmapMut, MmapOptions};
use parking_lot::Mutex;
use pyo3::exceptions::{PyFileNotFoundError, PyValueError};
use pyo3::prelude::*;
use std::fs::{File, OpenOptions};
use std::os::unix::fs::OpenOptionsExt;
use std::path::PathBuf;

/// Represents a shared memory region that can be used for IPC.
/// This is a simplified implementation that uses memory-mapped files.
pub struct SharedMemoryRegion {
    name: String,
    size: usize,
    file: File,
    mmap: MmapMut,
}

impl SharedMemoryRegion {
    /// Creates a new shared memory region or opens an existing one.
    pub fn create_or_open(name: &str, size: usize) -> PyResult<Self> {
        let path = get_shm_path(name);
        
        // Open or create the file
        let file = OpenOptions::new()
            .read(true)
            .write(true)
            .create(true)
            .truncate(false)
            .mode(0o600)
            .open(&path)
            .map_err(|e| PyValueError::new_err(format!("Failed to create/open shared memory file: {}", e)))?;

        // Set the file size if needed
        let metadata = file.metadata().map_err(|e| PyValueError::new_err(e.to_string()))?;
        if metadata.len() < size as u64 {
            file.set_len(size as u64)
                .map_err(|e| PyValueError::new_err(format!("Failed to set file size: {}", e)))?;
        }

        // Create the memory map
        let mmap = unsafe {
            MmapOptions::new()
                .map_mut(&file)
                .map_err(|e| PyValueError::new_err(format!("Failed to create memory map: {}", e)))?
        };

        Ok(Self {
            name: name.to_string(),
            size,
            file,
            mmap,
        })
    }

    /// Opens an existing shared memory region.
    pub fn open_existing(name: &str, size: usize) -> PyResult<Self> {
        let path = get_shm_path(name);
        
        let file = OpenOptions::new()
            .read(true)
            .write(true)
            .open(&path)
            .map_err(|e| PyFileNotFoundError::new_err(format!("Shared memory region '{}' does not exist: {}", name, e)))?;

        let mmap = unsafe {
            MmapOptions::new()
                .map_mut(&file)
                .map_err(|e| PyValueError::new_err(format!("Failed to create memory map: {}", e)))?
        };

        Ok(Self {
            name: name.to_string(),
            size,
            file,
            mmap,
        })
    }

    /// Returns the name of the shared memory region.
    pub fn name(&self) -> &str {
        &self.name
    }

    /// Returns the size of the shared memory region.
    pub fn size(&self) -> usize {
        self.size
    }

    /// Returns a mutable slice of bytes for direct access.
    pub fn bytes_mut(&mut self) -> &mut [u8] {
        &mut self.mmap
    }

    /// Closes the shared memory region.
    pub fn close(self) {
        // Dropping the MmapMut will unmap the memory
        // The File will be closed when dropped
    }
}

fn get_shm_path(name: &str) -> PathBuf {
    // Use /dev/shm on Linux for tmpfs-based shared memory
    PathBuf::from("/dev/shm").join(format!("directioner_{}", name))
}

/// Python wrapper for SharedMemoryRegion
#[pyclass]
pub struct PySharedMemoryRegion {
    inner: Mutex<Option<SharedMemoryRegion>>,
}

#[pymethods]
impl PySharedMemoryRegion {
    #[new]
    #[pyo3(signature = (name, bytes))]
    pub fn new(name: &str, bytes: usize) -> PyResult<Self> {
        let region = SharedMemoryRegion::create_or_open(name, bytes)?;
        Ok(Self {
            inner: Mutex::new(Some(region)),
        })
    }

    /// Returns the name of the shared memory region.
    pub fn name(&self) -> String {
        self.inner
            .lock()
            .as_ref()
            .map(|r| r.name().to_string())
            .unwrap_or_default()
    }

    /// Returns the size of the shared memory region.
    pub fn size(&self) -> usize {
        self.inner
            .lock()
            .as_ref()
            .map(|r| r.size())
            .unwrap_or(0)
    }

    /// Returns whether the region is mapped.
    pub fn mapped(&self) -> bool {
        self.inner.lock().is_some()
    }

    /// Closes the shared memory region.
    pub fn close(&self) {
        self.inner.lock().take();
    }

    /// Initializes a ring buffer in the shared memory region.
    /// This is a placeholder - actual ring buffer logic would be implemented here.
    pub fn initialize_ring(&self, capacity_bytes: usize) -> PyResult<()> {
        let guard = self.inner.lock();
        if guard.is_none() {
            return Err(PyValueError::new_err("Shared memory region is not open"));
        }
        // For now, just validate the capacity
        let region = guard.as_ref().unwrap();
        if capacity_bytes > region.size() {
            return Err(PyValueError::new_err(format!(
                "Capacity {} exceeds region size {}",
                capacity_bytes,
                region.size()
            )));
        }
        Ok(())
    }

    /// Reads a frame from the ring buffer.
    /// Returns None if no data is available.
    pub fn read_ring_frame(&self, max_bytes: usize) -> Option<Vec<u8>> {
        // Placeholder implementation - returns empty
        let _ = max_bytes;
        None
    }

    /// Writes a frame to the ring buffer.
    /// Returns true if successful.
    pub fn write_ring_frame(&self, payload: &[u8]) -> bool {
        // Placeholder implementation
        let _ = payload;
        false
    }
}

/// Calculates the required bytes for a ring buffer with the given capacity.
/// Formula: capacity + (next power of 2 of capacity) to handle wrap-around
#[pyfunction]
pub fn required_ring_bytes(capacity_bytes: usize) -> usize {
    let next_pow2 = capacity_bytes.next_power_of_two();
    capacity_bytes + next_pow2
}
