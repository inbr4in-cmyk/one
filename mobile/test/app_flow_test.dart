import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:one_english/api/api_client.dart';
import 'package:one_english/api/secret_store.dart';

import 'support/app_harness.dart';
import 'support/fake_backend.dart';

void main() {
  testWidgets('parent signs in with a WhatsApp code and sees the children', (tester) async {
    final be = FakeBackend();
    final h = await pumpApp(tester, be);
    expect(find.text('Вход'), findsOneWidget);

    await tester.enterText(find.byKey(const Key('phone')), '7052000001');
    await tester.pump();
    expect(find.text('705 200 00 01'), findsOneWidget);
    await tester.tap(find.text('Получить код'));
    await settle(tester);
    expect(be.requests.last.url.path, '/api/auth/otp/request');
    expect(be.bodies.last['phone'], '+77052000001');

    await tester.enterText(find.byKey(const Key('code')), '111111');
    await settle(tester);
    expect(find.text('Неверный код'), findsOneWidget);
    await tester.enterText(find.byKey(const Key('code')), '123456');
    await settle(tester);

    // A PIN is offered right after the first sign-in.
    expect(find.text('Придумайте PIN-код'), findsOneWidget);
    await tester.tap(find.text('Не сейчас'));
    await settle(tester);

    expect(find.textContaining('Гульнара'), findsWidgets);
    expect(find.textContaining('Арман'), findsWidgets);
    expect(find.textContaining('Алия'), findsWidgets);
    expect(await h.store.read(ApiClient.refreshKey), 'r1');
    await unmount(tester);
  });

  testWidgets('narrow screen (360×800) renders the login without overflow', (tester) async {
    await pumpApp(tester, FakeBackend(), size: const Size(360, 800));
    expect(find.text('Получить код'), findsOneWidget);
    expect(tester.takeException(), isNull);
    await unmount(tester);
  });

  testWidgets('updated rules block the app until accepted', (tester) async {
    final be = FakeBackend(rulesAccepted: '1.0', rulesVersion: '2.0', kind: 'student');
    final store = MemorySecretStore();
    await store.write(ApiClient.refreshKey, 'r1');
    await pumpApp(tester, be, store: store);
    expect(find.text('Правила обновились'), findsOneWidget);
    final accept = find.byKey(const Key('accept-rules'));
    await tester.tap(accept);
    await settle(tester, 5);
    expect(be.requests.where((r) => r.url.path == '/api/consents'), isEmpty);
    await tester.tap(find.byKey(const Key('agree')));
    await tester.pump();
    await tester.tap(accept);
    await settle(tester);
    expect(be.bodies[be.requests.indexWhere((r) => r.url.path == '/api/consents')]['document_id'], 9);
    expect(find.textContaining('Привет, Арман'), findsOneWidget);
    await unmount(tester);
  });

  testWidgets('blocked student: banner on home, homework closed', (tester) async {
    final be = FakeBackend(kind: 'student', blocked: true);
    final store = MemorySecretStore();
    await store.write(ApiClient.refreshKey, 'r1');
    await pumpApp(tester, be, store: store);
    expect(find.text('Доступ приостановлен'), findsWidgets);
    await tester.tap(find.byKey(const Key('tab/homework')));
    await settle(tester);
    expect(find.text('К оплате'), findsWidgets);
    expect(be.requests.where((r) => r.url.path.endsWith('/homework')), isEmpty);
    await unmount(tester);
  });
}
