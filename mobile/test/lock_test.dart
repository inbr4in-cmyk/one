import 'package:flutter_test/flutter_test.dart';
import 'package:one_english/api/secret_store.dart';
import 'package:one_english/state/lock.dart';
import 'package:one_english/state/settings.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  late LockController lock;
  late MemorySecretStore store;
  late Settings settings;

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    settings = Settings(await SharedPreferences.getInstance());
    store = MemorySecretStore();
    lock = LockController(store, settings);
  });

  test('simple PINs are refused', () {
    for (final p in ['1111', '1234', '4321', '0000', '1987', '2012', '12a4', '123']) {
      expect(LockController.weak(p), isTrue, reason: p);
    }
    for (final p in ['2580', '7391', '0429']) {
      expect(LockController.weak(p), isFalse, reason: p);
    }
  });

  test('the PIN is stored salted and hashed, and verifies', () async {
    await lock.setPin('7391');
    final stored = await store.read(LockController.pinKey);
    expect(stored, isNot(contains('7391')));
    expect(stored, contains(':'));
    final again = LockController(store, settings);
    await again.load();
    expect(again.pinSet, isTrue);
    again.lockNow();
    expect(again.locked, isTrue);
    expect(await again.verify('0000'), isFalse);
    expect(again.failures, 1);
    expect(await again.verify('7391'), isTrue);
    expect(again.locked, isFalse);
  });

  test('five wrong PINs end the session', () async {
    await lock.setPin('7391');
    var ended = 0;
    lock.onTooManyFailures = () => ended++;
    for (var i = 0; i < 5; i++) {
      await lock.verify('1590');
    }
    expect(ended, 1);
  });

  test('auto-lock after the configured delay; never without a PIN', () async {
    settings.autolockMinutes = 0;
    lock.paused();
    lock.resumed();
    expect(lock.locked, isFalse);
    await lock.setPin('7391');
    lock.paused();
    lock.resumed();
    expect(lock.locked, isTrue);
    await lock.verify('7391');
    settings.autolockMinutes = 5;
    lock.paused();
    lock.resumed();
    expect(lock.locked, isFalse);
  });
}
