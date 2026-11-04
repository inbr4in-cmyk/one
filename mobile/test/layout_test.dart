import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/date_symbol_data_local.dart';
import 'package:one_english/api/oe_api.dart';
import 'package:one_english/api/secret_store.dart';
import 'package:one_english/app.dart';
import 'package:one_english/demo/demo_backend.dart';
import 'package:one_english/router.dart';
import 'package:one_english/screens/home.dart' show LessonsTile;
import 'package:one_english/state/counters.dart';
import 'package:one_english/state/lock.dart';
import 'package:one_english/state/realtime.dart';
import 'package:one_english/state/session.dart';
import 'package:one_english/state/settings.dart';
import 'package:one_english/ui/widgets.dart' show kContentMaxWidth;
import 'package:shared_preferences/shared_preferences.dart';

import 'support/app_harness.dart' show settle, unmount;

/// Layout checks (QA H-20, H-21, C-17): the main screens over the demo data, with the real fonts, on small phones
/// with large text, in landscape and on a tablet. Any RenderFlex overflow fails the test and is listed.

Future<void> _loadFonts() async {
  final families = <String, List<String>>{
    'GolosText': ['400', '500', '600', '700'],
    'Unbounded': ['500', '600', '700'],
    'PlayfairDisplay': ['800'],
  };
  for (final e in families.entries) {
    final loader = FontLoader(e.key);
    for (final w in e.value) {
      final bytes = File('assets/fonts/${e.key}-$w.ttf').readAsBytesSync();
      loader.addFont(Future.value(ByteData.sublistView(bytes)));
    }
    await loader.load();
  }
}

class _Demo {
  _Demo(this.session, this.router);
  final Session session;
  final GoRouter router;
}

Future<_Demo> _pumpDemo(WidgetTester tester, String role, Size size, double scale) async {
  tester.view.physicalSize = size * 2;
  tester.view.devicePixelRatio = 2;
  tester.platformDispatcher.textScaleFactorTestValue = scale;
  addTearDown(tester.view.reset);
  addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
  SharedPreferences.setMockInitialValues({});
  final settings = Settings(await SharedPreferences.getInstance());
  final backend = DemoBackend();
  final secrets = MemorySecretStore();
  final api = OeApi(DemoApiClient(secrets: secrets, backend: backend));
  final lock = LockController(secrets, settings);
  final session = Session(api: api, settings: settings, lock: lock);
  final realtime = Realtime(api, connect: (_) => throw UnsupportedError('no socket in tests'));
  final counters = Counters(api, session, realtime);
  final router = buildRouter(session, lock);
  await tester.pumpWidget(OeApp(
      api: api, settings: settings, session: session, lock: lock, realtime: realtime, counters: counters, router: router));
  await tester.runAsync(session.boot);
  await settle(tester, 10);
  final phone = backend.phoneOf(role);
  await tester.runAsync(() async {
    await session.requestCode(phone);
    await session.verifyCode(phone, DemoBackend.code);
  });
  await settle(tester, 10);
  return _Demo(session, router);
}

/// Runs [body] and returns every overflow reported while it ran, with the screen it happened on.
Future<List<String>> _overflows(Future<void> Function(void Function(String) at) body) async {
  final found = <String>[];
  var where = '';
  final prev = FlutterError.onError;
  FlutterError.onError = (d) {
    final msg = d.exceptionAsString();
    if (msg.contains('overflowed')) {
      found.add('$where: ${msg.split('\n').first}');
      if (Platform.environment['OE_LAYOUT_DEBUG'] != null) debugPrint('---- $where\n${d.toString()}');
    } else {
      prev?.call(d);
    }
  };
  try {
    await body((s) => where = s);
  } finally {
    FlutterError.onError = prev;
  }
  return found;
}

Future<void> _visit(WidgetTester tester, _Demo d, void Function(String) at, List<String> routes) async {
  for (final r in routes) {
    at(r);
    if (r.startsWith('/progress') || r.startsWith('/coins/') || r.startsWith('/security') || r.startsWith('/rules')) {
      d.router.push(r);
    } else {
      d.router.go(r);
    }
    await settle(tester, 12);
    if (r.startsWith('/progress') || r.startsWith('/coins/') || r.startsWith('/security') || r.startsWith('/rules')) {
      d.router.pop();
      await settle(tester, 4);
    }
  }
}

const _studentRoutes = ['/home', '/schedule', '/homework', '/chats', '/coins', '/notifications', '/profile', '/progress', '/coins/history'];
const _parentRoutes = ['/home', '/payments', '/chats', '/notifications', '/profile', '/schedule', '/homework', '/coins', '/progress', '/security'];

void main() {
  setUpAll(() async {
    await initializeDateFormatting();
    await _loadFonts();
  });

  for (final size in const [Size(320, 568), Size(360, 800)]) {
    for (final scale in const [1.0, 1.3, 2.0]) {
      for (final role in const ['student', 'parent']) {
        testWidgets('no overflow: $role at ${size.width.toInt()}×${size.height.toInt()}, text ×$scale', (tester) async {
          final errors = await _overflows((at) async {
            at('pin setup');
            final d = await _pumpDemo(tester, role, size, scale);
            expect(find.byKey(const Key('pin-1')), findsOneWidget);
            at('/home');
            d.session.pinOffered();
            await settle(tester, 6);
            if (d.session.needsRules) {
              await tester.runAsync(d.session.acceptRules);
              await settle(tester, 6);
            }
            await _visit(tester, d, at, role == 'student' ? _studentRoutes : _parentRoutes);
          });
          expect(errors, isEmpty, reason: errors.join('\n'));
          await unmount(tester);
        });
      }
    }
  }

  for (final size in const [Size(667, 375), Size(844, 390), Size(568, 320)]) {
    testWidgets('PIN setup in landscape ${size.width.toInt()}×${size.height.toInt()}: title, dots and keys visible', (tester) async {
      final errors = await _overflows((at) async {
        at('pin setup');
        await _pumpDemo(tester, 'student', size, 1.0);
        final screen = Offset.zero & size;
        for (final k in ['pin-1', 'pin-0', 'pin-9']) {
          expect(screen.contains(tester.getRect(find.byKey(Key(k))).bottomRight - const Offset(1, 1)), isTrue, reason: k);
        }
        final title = find.text('Придумайте PIN-код');
        expect(title, findsOneWidget);
        expect(screen.contains(tester.getRect(title).center), isTrue);
        expect(screen.contains(tester.getRect(find.byKey(const Key('pin-dots'))).center), isTrue);
      });
      expect(errors, isEmpty, reason: errors.join('\n'));
      await unmount(tester);
    });
  }

  for (final role in const ['student', 'parent']) {
    testWidgets('tablet 1024×768: $role home is limited to a centred readable width', (tester) async {
      final errors = await _overflows((at) async {
        final d = await _pumpDemo(tester, role, const Size(1024, 768), 1.0);
        at('/home');
        d.session.pinOffered();
        await settle(tester, 6);
        if (d.session.needsRules) {
          await tester.runAsync(d.session.acceptRules);
          await settle(tester, 6);
        }
        d.router.go('/home');
        await settle(tester, 12);
        final tile = tester.getRect(find.byType(LessonsTile));
        // Two tiles side by side in at most 640 px, centred on the 1024 px screen.
        expect(tile.left, greaterThanOrEqualTo((1024 - kContentMaxWidth) / 2));
        expect(tile.width, lessThan(kContentMaxWidth / 2));
      });
      expect(errors, isEmpty, reason: errors.join('\n'));
      await unmount(tester);
    });
  }
}
