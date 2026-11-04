import 'dart:ui';

import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:go_router/go_router.dart';
import 'package:provider/provider.dart';

import 'api/oe_api.dart';
import 'l10n/l10n.dart';
import 'state/counters.dart';
import 'state/lock.dart';
import 'state/realtime.dart';
import 'state/session.dart';
import 'state/settings.dart';
import 'ui/icons.dart';
import 'ui/theme.dart';
import 'ui/widgets.dart' show kMaxTextScale;

class OeApp extends StatefulWidget {
  const OeApp({super.key, required this.api, required this.settings, required this.session, required this.lock,
      required this.realtime, required this.counters, required this.router});
  final OeApi api;
  final Settings settings;
  final Session session;
  final LockController lock;
  final Realtime realtime;
  final Counters counters;
  final GoRouter router;

  @override
  State<OeApp> createState() => _OeAppState();
}

class _OeAppState extends State<OeApp> with WidgetsBindingObserver {
  bool _hidden = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    // In the app switcher chats and payments are covered by the logo (design 16).
    setState(() => _hidden = state != AppLifecycleState.resumed);
    if (state == AppLifecycleState.paused) widget.lock.paused();
    if (state == AppLifecycleState.resumed) {
      widget.lock.resumed();
      if (widget.session.ready) {
        widget.realtime.wake();
        widget.counters.refresh();
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return MultiProvider(
      providers: [
        Provider.value(value: widget.api),
        Provider.value(value: widget.realtime),
        ChangeNotifierProvider.value(value: widget.settings),
        ChangeNotifierProvider.value(value: widget.session),
        ChangeNotifierProvider.value(value: widget.lock),
        ChangeNotifierProvider.value(value: widget.counters),
      ],
      child: Consumer<Settings>(
        builder: (context, s, _) => MaterialApp.router(
          title: 'One English',
          debugShowCheckedModeBanner: false,
          theme: buildTheme(Brightness.light),
          darkTheme: buildTheme(Brightness.dark),
          themeMode: s.theme,
          locale: s.flutterLocale,
          supportedLocales: AppLocalizations.supportedLocales,
          localizationsDelegates: const [
            AppLocalizations.delegate,
            GlobalMaterialLocalizations.delegate,
            GlobalCupertinoLocalizations.delegate,
            GlobalWidgetsLocalizations.delegate,
          ],
          routerConfig: widget.router,
          // System text size is followed up to 200 %; tight elements cap themselves lower (TightText).
          builder: (context, child) => MediaQuery.withClampedTextScaling(
            maxScaleFactor: kMaxTextScale,
            child: Stack(children: [
              child ?? const SizedBox(),
              if (_hidden) const _PrivacyCover(),
            ]),
          ),
        ),
      ),
    );
  }
}

class _PrivacyCover extends StatelessWidget {
  const _PrivacyCover();

  @override
  Widget build(BuildContext context) => Positioned.fill(
        child: ClipRect(
          child: BackdropFilter(
            filter: ImageFilter.blur(sigmaX: 18, sigmaY: 18),
            child: Container(
              color: context.oe.paper.withValues(alpha: .7),
              alignment: Alignment.center,
              child: const OeLogoMark(width: 96),
            ),
          ),
        ),
      );
}
