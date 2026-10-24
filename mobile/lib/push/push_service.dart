import 'dart:async';

import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/foundation.dart';

import '../api/oe_api.dart';
import '../state/session.dart';
import '../state/settings.dart';

/// Push through Firebase Cloud Messaging (APNs on iOS).
///
/// Firebase is configured natively (android/app/google-services.json, ios/Runner/GoogleService-Info.plist —
/// not in the repo, see mobile/README). Without them [init] fails quietly and the app works without push.
class PushService {
  PushService(this.api, this.session, this.settings, {required this.open});

  final OeApi api;
  final Session session;
  final Settings settings;

  /// Opens an app route for a tapped notification.
  final void Function(String? link) open;

  bool available = false;
  String? _token;
  StreamSubscription<String>? _refresh;

  String get _platform => defaultTargetPlatform == TargetPlatform.iOS ? 'ios' : 'android';

  Future<void> init() async {
    if (kIsWeb) return;
    try {
      await Firebase.initializeApp();
      available = true;
    } catch (e) {
      debugPrint('push: Firebase is not configured, push disabled');
      return;
    }
    final fm = FirebaseMessaging.instance;
    FirebaseMessaging.onMessageOpenedApp.listen((m) => open(m.data['link'] as String?));
    final initial = await fm.getInitialMessage();
    if (initial != null) open(initial.data['link'] as String?);
    session.onSignedIn.add(register);
    session.onSigningOut.add(unregister);
    settings.addListener(_localeChanged);
  }

  String? _lastLocale;
  void _localeChanged() {
    if (_lastLocale != null && _lastLocale != settings.locale && session.ready) register();
    _lastLocale = settings.locale;
  }

  /// Ask permission, then POST /api/auth/devices {platform, token, locale}. The token belongs to this session.
  Future<void> register() async {
    if (!available) return;
    final fm = FirebaseMessaging.instance;
    final perm = await fm.requestPermission();
    if (perm.authorizationStatus == AuthorizationStatus.denied) return;
    // The backend sends through FCM HTTP v1 to registration tokens, so keep getToken() until it moves to FID direct-send.
    // ignore: deprecated_member_use
    final token = await fm.getToken();
    if (token == null) return;
    _token = token;
    _lastLocale = settings.locale;
    await api.registerDevice(_platform, token, settings.locale);
    // ignore: deprecated_member_use
    _refresh ??= fm.onTokenRefresh.listen((t) {
      _token = t;
      if (session.ready) api.registerDevice(_platform, t, settings.locale).catchError((_) {});
    });
  }

  Future<void> unregister() async {
    final t = _token;
    if (!available || t == null) return;
    try {
      await api.unregisterDevice(t);
    } catch (_) {}
    _token = null;
  }
}
