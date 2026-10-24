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

  testWidgets('student: a phone number blocks sending without dropping the keyboard', (tester) async {
    final (be, _) = await signedIn(tester, 'student');
    be.overrides['GET /chats/7/messages'] = (_) => [];
    be.overrides['GET /chats/7/pinned'] = (_) => [];
    be.overrides['POST /chats/7/read'] = (_) => {'ok': true};
    Object? sent;
    be.overrides['POST /chats/7/messages'] = (r) {
      sent = r.body;
      return {'id': 99, 'chat_id': 7, 'sender_id': 1, 'sender_name': 'Арман Ахметов', 'kind': 'text', 'text': 'Добрый вечер', 'at': DateTime.now().toUtc().toIso8601String()};
    };
    await tester.tap(find.byKey(const Key('tab/chats')));
    await settle(tester);
    await tester.tap(find.text('PI-3'));
    await settle(tester);
    if (find.text('Понятно').evaluate().isNotEmpty) {
      await tester.tap(find.text('Понятно'));
      await settle(tester, 10);
    }
    final composer = find.byKey(const Key('composer'));
    await tester.tap(composer);
    await tester.enterText(composer, 'Мой номер +7 701 234 56 78');
    await tester.pump();
    expect(find.text('Номер телефона в сообщении'), findsOneWidget);
    // The field kept its state and focus when the warning appeared above it.
    final editable = tester.widget<EditableText>(find.descendant(of: composer, matching: find.byType(EditableText)));
    expect(editable.focusNode.hasFocus, isTrue);
    expect(editable.controller.text, 'Мой номер +7 701 234 56 78');
    await tester.tap(find.byKey(const Key('send')));
    await tester.pump();
    expect(sent, isNull);
    await tester.tap(find.text('Убрать номер'));
    await tester.pump();
    expect(find.text('Мой номер'), findsOneWidget);
    expect(find.text('Номер телефона в сообщении'), findsNothing);
    await tester.tap(find.byKey(const Key('send')));
    await settle(tester, 10);
    expect(sent, contains('Мой номер'));
    await unmount(tester);
  });

  testWidgets('server rejection of a message is shown; staff position tags the sender', (tester) async {
    final (be, _) = await signedIn(tester, 'student');
    final at = DateTime.now().toUtc().toIso8601String();
    be.overrides['GET /chats/7/messages'] = (_) => [
          {'id': 5, 'chat_id': 7, 'sender_id': 60, 'sender_name': 'Динара Сапарова', 'sender_kind': 'staff', 'sender_position': 'Менеджер', 'kind': 'text', 'text': 'Добрый день', 'at': at}
        ];
    be.overrides['GET /chats/7/pinned'] = (_) => [];
    be.overrides['POST /chats/7/read'] = (_) => {'ok': true};
    be.overrides['POST /chats/7/messages'] = (_) => throw const _Reject();
    await tester.tap(find.byKey(const Key('tab/chats')));
    await settle(tester);
    await tester.tap(find.text('PI-3'));
    await settle(tester);
    if (find.text('Понятно').evaluate().isNotEmpty) {
      await tester.tap(find.text('Понятно'));
      await settle(tester, 10);
    }
    expect(find.textContaining('Менеджер'), findsOneWidget);
    await tester.enterText(find.byKey(const Key('composer')), 'пишите мне восемь семь ноль один');
    await tester.pump();
    await tester.tap(find.byKey(const Key('send')));
    await settle(tester, 10);
    expect(find.text('Сообщение не отправлено'), findsOneWidget);
    expect(find.text('Нельзя отправлять номера телефонов'), findsOneWidget);
    await tester.enterText(find.byKey(const Key('composer')), 'хорошо');
    await tester.pump();
    expect(find.text('Сообщение не отправлено'), findsNothing);
    await unmount(tester);
  });

  testWidgets('books: owned and still needed for the level', (tester) async {
    final (be, _) = await signedIn(tester, 'parent');
    be.overrides['GET /students/3/books'] = (_) => {
          'items': [
            {'at': '2026-09-02T10:00:00Z', 'book_id': 1, 'title': 'Family & Friends 2 — Class Book', 'qty': 1, 'price': '6500.00'}
          ],
          'needed': [
            {'id': 2, 'title': 'Family & Friends 2 — Workbook', 'price': 4500}
          ],
        };
    await tester.tap(find.byKey(const Key('tab/profile')));
    await settle(tester);
    await tester.tap(find.text('Учебники'));
    await settle(tester);
    expect(find.text('Нужны для уровня'), findsOneWidget);
    expect(find.text('Family & Friends 2 — Workbook'), findsOneWidget);
    expect(find.text('Уже есть'), findsOneWidget);
    expect(find.text('Family & Friends 2 — Class Book'), findsOneWidget);
    expect(find.textContaining('6'), findsWidgets);
    await unmount(tester);
  });

  testWidgets("parent's chats are grouped by about_student_id", (tester) async {
    final (be, _) = await signedIn(tester, 'parent');
    final at = DateTime.now().toUtc().toIso8601String();
    be.overrides['GET /chats'] = (_) => [
          {'id': 21, 'kind': 'direct', 'title': 'Динара Сапарова', 'unread': 0, 'about_student_id': 4,
           'other_user': {'id': 60, 'full_name': 'Динара Сапарова', 'kind': 'staff', 'position': 'Менеджер'},
           'last_message': {'text': 'Про Алию', 'at': at}},
          {'id': 22, 'kind': 'direct', 'title': 'Офис', 'unread': 0,
           'other_user': {'id': 61, 'full_name': 'Офис', 'kind': 'staff'}, 'last_message': {'text': 'Общее', 'at': at}},
        ];
    await tester.tap(find.byKey(const Key('tab/chats')));
    await settle(tester);
    final alia = tester.getTopLeft(find.text('АЛИЯ · PI-3')).dy;
    final school = tester.getTopLeft(find.text('ФИЛИАЛ САМАЛ')).dy;
    final aboutAlia = tester.getTopLeft(find.text('Про Алию')).dy;
    final general = tester.getTopLeft(find.text('Общее')).dy;
    expect(alia < aboutAlia && aboutAlia < school && school < general, isTrue);
    expect(find.textContaining('АРМАН ·'), findsNothing);
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

/// Makes the fake backend answer 400 with a reason, as the server does for a student's phone number.
class _Reject implements Exception {
  const _Reject();
}
