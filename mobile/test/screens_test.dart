import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:one_english/api/api_client.dart';
import 'package:one_english/api/secret_store.dart';

import 'support/app_harness.dart';
import 'support/fake_backend.dart';

Future<(FakeBackend, Harness)> signedIn(WidgetTester tester, String kind) async {
  final be = FakeBackend(kind: kind);
  final due = DateTime.now().toUtc().add(const Duration(days: 2)).toIso8601String();
  be.overrides['GET /portal/students/3/homework'] = (_) => [
        {'id': 1, 'title': 'Unit 5 — Past Simple', 'body': 'Упражнения 3–5', 'due_at': due, 'status': 'assigned'}
      ];
  be.overrides['GET /chats'] = (_) => [
        {
          'id': 7,
          'kind': 'group',
          'title': 'PI-3',
          'group_id': 10,
          'unread': 2,
          'members': 9,
          'last_message': {'text': 'Не забудьте тетради', 'sender_name': 'Айгерим Нурланова', 'at': DateTime.now().toUtc().toIso8601String()}
        }
      ];
  final store = MemorySecretStore();
  await store.write(ApiClient.refreshKey, 'r1');
  final h = await pumpApp(tester, be, store: store);
  return (be, h);
}

void main() {
  testWidgets('student submits a homework answer', (tester) async {
    final (be, _) = await signedIn(tester, 'student');
    Object? sent;
    be.overrides['POST /portal/homework/1/submit'] = (r) {
      sent = r.body;
      return {'ok': true};
    };
    await tester.tap(find.byKey(const Key('tab/homework')));
    await settle(tester);
    expect(find.text('Unit 5 — Past Simple'), findsOneWidget);
    await tester.tap(find.text('Unit 5 — Past Simple'));
    await settle(tester);
    await tester.enterText(find.byKey(const Key('hw-answer')), 'I went to school yesterday.');
    await tester.pump();
    await tester.ensureVisible(find.byKey(const Key('hw-submit')));
    await tester.tap(find.byKey(const Key('hw-submit')));
    await settle(tester);
    expect(sent, contains('"student_id":3'));
    expect(sent, contains('I went to school yesterday.'));
    expect(find.text('Задание отправлено на проверку'), findsOneWidget);
    await unmount(tester);
  });

  testWidgets('chat list shows the group chat with unread count', (tester) async {
    await signedIn(tester, 'student');
    await tester.tap(find.byKey(const Key('tab/chats')));
    await settle(tester);
    expect(find.text('PI-3'), findsOneWidget);
    expect(find.textContaining('Не забудьте тетради'), findsOneWidget);
    expect(find.text('2'), findsWidgets);
    await unmount(tester);
  });

  testWidgets('parent switches the app to Kazakh in the profile', (tester) async {
    await signedIn(tester, 'parent');
    await tester.tap(find.byKey(const Key('tab/profile')));
    await settle(tester);
    await tester.tap(find.text('Қаз'));
    await settle(tester);
    expect(find.text('Басты'), findsWidgets);
    expect(find.text('Тіл'), findsOneWidget);
    await unmount(tester);
  });
}
