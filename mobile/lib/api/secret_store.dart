import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// Small key-value store for secrets (refresh token, PIN hash). Keychain on iOS, Keystore-backed on Android.
abstract class SecretStore {
  Future<String?> read(String key);
  Future<void> write(String key, String? value);
  Future<void> deleteAll();
}

class SecureSecretStore implements SecretStore {
  SecureSecretStore() : _s = const FlutterSecureStorage(
          iOptions: IOSOptions(accessibility: KeychainAccessibility.first_unlock_this_device),
        );
  final FlutterSecureStorage _s;

  @override
  Future<String?> read(String key) async {
    try {
      return await _s.read(key: key);
    } catch (_) {
      // A corrupted keystore entry (e.g. after a device restore) means "signed out", not a crash.
      return null;
    }
  }

  @override
  Future<void> write(String key, String? value) =>
      value == null ? _s.delete(key: key) : _s.write(key: key, value: value);

  @override
  Future<void> deleteAll() => _s.deleteAll();
}

/// In-memory store for tests.
class MemorySecretStore implements SecretStore {
  final Map<String, String> data = {};

  @override
  Future<String?> read(String key) async => data[key];

  @override
  Future<void> write(String key, String? value) async {
    if (value == null) {
      data.remove(key);
    } else {
      data[key] = value;
    }
  }

  @override
  Future<void> deleteAll() async => data.clear();
}
