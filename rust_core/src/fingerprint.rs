//! High-throughput SHA-256 batch fingerprinting in Rust.

use sha2::{Digest, Sha256};

/// Computes SHA-256 hexadecimal hash over raw contiguous byte slices.
pub fn compute_sha256_hex(bytes: &[u8]) -> String {
    let mut hasher = Sha256::new();
    hasher.update(bytes);
    format!("{:x}", hasher.finalize())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_sha256_empty() {
        let h = compute_sha256_hex(b"");
        assert_eq!(h, "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855");
    }

    #[test]
    fn test_sha256_known_string() {
        let h = compute_sha256_hex(b"hello world");
        assert_eq!(h, "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9");
    }
}
