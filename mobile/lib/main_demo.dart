import 'package:flutter/material.dart';
import 'package:intl/date_symbol_data_local.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'api/oe_api.dart';
import 'api/secret_store.dart';
import 'app.dart';
import 'demo/demo_backend.dart';
import 'router.dart';
import 'screens/auth.dart';
import 'state/counters.dart';
import 'state/lock.dart';
import 'state/realtime.dart';
import 'state/session.dart';
import 'state/settings.dart';
import 'ui/icons.dart';
import 'ui/theme.dart';
import 'ui/widgets.dart';

/// Offline demo: the same app over an in-memory backend ([DemoBackend]).
///
/// Build: `flutter build web --release -t lib/main_demo.dart` (see tool/build_demo.sh). Nothing here opens a
/// network connection: no realtime socket, no push, every API call is answered by the recorded fixtures.
Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await initializeDateFormatting();
  final settings = Settings(await _prefs());
  final backend = DemoBackend();
  // The demo keeps tokens and the PIN in memory: a reload starts from the welcome screen.
  final secrets = MemorySecretStore();
  final api = OeApi(DemoApiClient(secrets: secrets, backend: backend));
  final lock = LockController(secrets, settings);
  final session = Session(api: api, settings: settings, lock: lock);
  final realtime = Realtime(api); // never started: the demo has no socket
  final counters = Counters(api, session, realtime);
  session.onSignedIn.add(() async => counters.start());
  session.onSigningOut.add(() async => counters.stop());
  final router = buildRouter(session, lock);

  runApp(
    DemoFrame(
      backend: backend,
      session: session,
      settings: settings,
      child: OeApp(
        api: api,
        settings: settings,
        session: session,
        lock: lock,
        realtime: realtime,
        counters: counters,
        router: router,
      ),
    ),
  );
  await session.boot();
}

/// Browser storage can be unavailable (private mode, sandboxed frames); the demo then keeps settings in memory.
Future<SharedPreferences> _prefs() async {
  try {
    return await SharedPreferences.getInstance();
  } catch (_) {
    // ignore: invalid_use_of_visible_for_testing_member
    SharedPreferences.setMockInitialValues({});
    return SharedPreferences.getInstance();
  }
}

/// Demo-only strings (the regular app texts stay in the ARB files).
class _T {
  _T(this.kk);
  final bool kk;
  String get badge => kk ? 'Демо-нұсқа' : 'Демо-версия';
  String get badgeCode => 'Демо · код 111111';
  String get title => kk ? 'Қосымшаның демо-нұсқасы' : 'Демо-версия приложения';
  String get lead => kk
      ? 'Мектептің шынайы деректеріне ұқсас мысалдар. Барлық әрекет тек осы құрылғыда қалады.'
      : 'Данные похожи на настоящие, но это пример. Всё, что вы сделаете, останется только на этом устройстве.';
  String get parent => kk ? 'Ата-ана ретінде кіру' : 'Войти как родитель';
  String get parentHint => kk ? 'Екі бала, сабақ кестесі, төлемдер, чат' : 'Двое детей, расписание, оплаты, чаты';
  String get student => kk ? 'Оқушы ретінде кіру' : 'Войти как ученик';
  String get studentHint => kk ? 'Үй тапсырмасы, коиндер, дүкен, топ чаты' : 'Домашка, коины, магазин, чат группы';
  String get phone => kk ? 'Телефон нөмірі арқылы кіру' : 'Войти по номеру телефона';
  String get phoneHint => kk ? 'Кез келген нөмір, код — 111111' : 'Любой номер, код — 111111';
}

/// Wraps the app with the demo welcome screen (while signed out) and a small «Демо-версия» marker.
class DemoFrame extends StatefulWidget {
  const DemoFrame({
    super.key,
    required this.backend,
    required this.session,
    required this.settings,
    required this.child,
  });
  final DemoBackend backend;
  final Session session;
  final Settings settings;
  final Widget child;

  @override
  State<DemoFrame> createState() => _DemoFrameState();
}

class _DemoFrameState extends State<DemoFrame> {
  bool _manual = false;
  String? _busy;
  String? _error;

  bool _firstFrame = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) setState(() => _firstFrame = true);
    });
    widget.session.addListener(_changed);
    widget.settings.addListener(_changed);
  }

  @override
  void dispose() {
    widget.session.removeListener(_changed);
    widget.settings.removeListener(_changed);
    super.dispose();
  }

  Stage? _lastStage;

  void _changed() {
    if (!mounted) return;
    setState(() {
      final stage = widget.session.stage;
      if (stage == Stage.ready) _busy = null;
      // After a logout the welcome screen comes back.
      if (stage == Stage.signedOut && _lastStage != null && _lastStage != Stage.signedOut) _manual = false;
      _lastStage = stage;
    });
  }

  Future<void> _signIn(String role) async {
    setState(() {
      _busy = role;
      _error = null;
    });
    try {
      final phone = widget.backend.phoneOf(role);
      await widget.session.requestCode(phone);
      await widget.session.verifyCode(phone, DemoBackend.code);
    } catch (e) {
      if (mounted) {
        setState(() {
          _busy = null;
          _error = '$e';
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = _T(widget.settings.locale == 'kk');
    final signedOut = widget.session.stage == Stage.signedOut;
    final welcome = signedOut && !_manual;
    return Directionality(
      textDirection: TextDirection.ltr,
      child: Column(
        children: [
          _Badge(text: signedOut && _manual ? t.badgeCode : t.badge),
          Expanded(
            child: Stack(
              children: [
                // While the welcome screen covers the app, the login screen below takes no focus and is not announced.
                ExcludeSemantics(
                  excluding: welcome,
                  child: ExcludeFocus(excluding: welcome, child: widget.child),
                ),
                // Added after the first frame: the browser can focus the view before that frame, and focus traversal
                // must not meet a second, not yet laid out app.
                if (_firstFrame)
                  Positioned.fill(
                    child: Offstage(
                      offstage: !welcome,
                      child: ExcludeFocus(
                        excluding: !welcome,
                        child: MaterialApp(
                          debugShowCheckedModeBanner: false,
                          theme: buildTheme(Brightness.light),
                          darkTheme: buildTheme(Brightness.dark),
                          themeMode: widget.settings.theme,
                          home: _Welcome(
                            t: t,
                            busy: _busy,
                            error: _error,
                            onRole: _signIn,
                            onPhone: () => setState(() => _manual = true),
                          ),
                        ),
                      ),
                    ),
                  ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

/// A thin strip above the app: always visible, never covers the app's own content.
class _Badge extends StatelessWidget {
  const _Badge({required this.text});
  final String text;

  @override
  Widget build(BuildContext context) {
    final top = MediaQueryData.fromView(View.of(context)).padding.top;
    return Container(
      width: double.infinity,
      color: const Color(0xFF0F2350),
      padding: EdgeInsets.only(top: top),
      height: top + 16,
      alignment: Alignment.center,
      child: Text(
        text,
        style: const TextStyle(
          fontFamily: kText,
          fontSize: 10,
          height: 1.2,
          fontWeight: FontWeight.w600,
          color: Color(0xE6FFFFFF),
          decoration: TextDecoration.none,
          letterSpacing: .4,
        ),
      ),
    );
  }
}

class _Welcome extends StatelessWidget {
  const _Welcome({
    required this.t,
    required this.busy,
    required this.error,
    required this.onRole,
    required this.onPhone,
  });
  final _T t;
  final String? busy;
  final String? error;
  final void Function(String role) onRole;
  final VoidCallback onPhone;

  @override
  Widget build(BuildContext context) {
    final oe = context.oe;
    return Scaffold(
      backgroundColor: oe.paper,
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.fromLTRB(24, 32, 24, 24),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 420),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  const Center(child: OeLogoMark(width: 64)),
                  const SizedBox(height: 14),
                  const Center(child: Wordmark(size: 24)),
                  const SizedBox(height: 28),
                  Text(
                    t.title,
                    textAlign: TextAlign.center,
                    style: display(20, color: oe.ink),
                  ),
                  const SizedBox(height: 8),
                  Text(
                    t.lead,
                    textAlign: TextAlign.center,
                    style: TextStyle(color: oe.muted, fontSize: 14, height: 1.4),
                  ),
                  const SizedBox(height: 28),
                  OeButton(
                    t.parent,
                    loading: busy == 'parent',
                    onPressed: busy == null ? () => onRole('parent') : null,
                  ),
                  _hint(context, t.parentHint),
                  const SizedBox(height: 12),
                  OeButton(
                    t.student,
                    kind: BtnKind.tonal,
                    loading: busy == 'student',
                    onPressed: busy == null ? () => onRole('student') : null,
                  ),
                  _hint(context, t.studentHint),
                  const SizedBox(height: 20),
                  OeButton(t.phone, kind: BtnKind.ghost, onPressed: busy == null ? onPhone : null),
                  _hint(context, t.phoneHint),
                  if (error != null) ...[
                    const SizedBox(height: 12),
                    Text(
                      error!,
                      textAlign: TextAlign.center,
                      style: TextStyle(color: oe.red, fontSize: 13),
                    ),
                  ],
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _hint(BuildContext context, String s) => Padding(
    padding: const EdgeInsets.only(top: 6),
    child: Text(
      s,
      textAlign: TextAlign.center,
      style: TextStyle(color: context.oe.muted, fontSize: 12.5),
    ),
  );
}
