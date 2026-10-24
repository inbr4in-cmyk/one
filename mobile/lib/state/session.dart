import 'package:flutter/foundation.dart';

import '../api/api_client.dart';
import '../api/models.dart';
import '../api/oe_api.dart';
import 'lock.dart';
import 'settings.dart';

enum Stage { booting, signedOut, offline, ready }

/// Who is signed in, which child the screens show, and whether the rules gate applies.
class Session extends ChangeNotifier {
  Session({required this.api, required this.settings, required this.lock}) {
    api.client.onAuthLost = () => signOut(remote: false);
    lock.onTooManyFailures = () {
      lockExpired = true;
      signOut();
    };
  }

  final OeApi api;
  final Settings settings;
  final LockController lock;

  Stage stage = Stage.booting;
  AuthMe? me;
  PortalMe? portal;
  DocVersion? rules;
  int? _childId;

  /// Just signed in with a code: offer to create a PIN.
  bool offerPin = false;

  /// The account is staff: the app is only for students and parents.
  bool staffRejected = false;

  /// Signed out because of too many wrong PINs (the login screen explains).
  bool lockExpired = false;

  /// A push link opened before the app was unlocked; followed once ready.
  String? pendingLink;

  /// Hooks run after sign-in and before sign-out (push token, realtime).
  final List<Future<void> Function()> onSignedIn = [];
  final List<Future<void> Function()> onSigningOut = [];

  bool get ready => stage == Stage.ready && me != null;
  bool get isParent => me?.isParent ?? false;
  bool get isStudent => me?.isStudent ?? false;
  List<Child> get children => portal?.children ?? const [];

  Child? get child {
    final list = children;
    if (list.isEmpty) return null;
    return list.firstWhere((c) => c.id == _childId, orElse: () => list.first);
  }

  bool get needsRules => rules != null && me != null && me!.rulesAcceptedVersion != rules!.version;

  void selectChild(int id) {
    if (!children.any((c) => c.id == id) || id == child?.id) return;
    _childId = id;
    settings.childId = id;
    notifyListeners();
  }

  Future<void> boot() async {
    await lock.load();
    if (!await api.client.hasStoredSession()) {
      stage = Stage.signedOut;
      notifyListeners();
      return;
    }
    try {
      if (!await api.client.refresh()) throw ApiException(401, '');
      await _load();
      stage = Stage.ready;
      lock.lockNow();
      notifyListeners();
      await _runSignedIn();
    } on ApiException catch (e) {
      if (e.isNetwork || e.status >= 500) {
        stage = Stage.offline;
      } else {
        await _reset();
        stage = Stage.signedOut;
      }
      notifyListeners();
    }
  }

  Future<void> retryBoot() async {
    stage = Stage.booting;
    notifyListeners();
    await boot();
  }

  Future<void> requestCode(String phone) => api.otpRequest(phone);

  /// Verify the WhatsApp code and load the cabinet. Staff accounts are signed out again.
  Future<void> verifyCode(String phone, String code) async {
    await api.otpVerify(phone, code);
    try {
      await _load();
    } catch (_) {
      await api.client.clearTokens();
      rethrow;
    }
    if (!me!.isPortal) {
      staffRejected = true;
      await signOut();
      return;
    }
    lockExpired = false;
    staffRejected = false;
    offerPin = !lock.pinSet;
    stage = Stage.ready;
    notifyListeners();
    await _runSignedIn();
  }

  Future<void> _load() async {
    me = await api.authMe();
    if (!me!.isPortal) return;
    portal = await api.portalMe();
    _childId = settings.childId;
    try {
      rules = await api.document('rules');
    } on ApiException catch (e) {
      if (e.isNetwork) rethrow;
      rules = null;
    }
  }

  Future<void> _runSignedIn() async {
    for (final f in onSignedIn) {
      try {
        await f();
      } catch (_) {}
    }
  }

  /// Refresh the overview (balances, coins, blocked) after payments and orders.
  Future<void> reloadPortal() async {
    try {
      portal = await api.portalMe();
      notifyListeners();
    } catch (_) {}
  }

  Future<void> acceptRules() async {
    final r = rules;
    if (r == null) return;
    final v = await api.acceptDocument(r.id);
    me?.rulesAcceptedVersion = v;
    notifyListeners();
  }

  void pinOffered() {
    offerPin = false;
    notifyListeners();
  }

  bool _signingOut = false;

  Future<void> signOut({bool remote = true}) async {
    if (_signingOut) return;
    _signingOut = true;
    try {
      for (final f in onSigningOut) {
        try {
          await f();
        } catch (_) {}
      }
      if (remote && api.client.hasAccess) {
        try {
          await api.logout();
        } catch (_) {}
      }
      await _reset();
      stage = Stage.signedOut;
      notifyListeners();
    } finally {
      _signingOut = false;
    }
  }

  Future<void> _reset() async {
    await api.client.clearTokens();
    await lock.clear();
    await settings.clearAccount();
    me = null;
    portal = null;
    rules = null;
    _childId = null;
    offerPin = false;
    pendingLink = null;
  }
}
