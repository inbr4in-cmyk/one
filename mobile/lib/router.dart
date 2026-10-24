import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import 'push/links.dart';
import 'screens/auth.dart';
import 'screens/chats.dart';
import 'screens/coins.dart';
import 'screens/feedback.dart';
import 'screens/home.dart';
import 'screens/homework.dart';
import 'screens/notifications.dart';
import 'screens/payments.dart';
import 'screens/pin.dart';
import 'screens/profile.dart';
import 'screens/progress.dart';
import 'screens/rules.dart';
import 'screens/schedule.dart';
import 'screens/shell.dart';
import 'state/lock.dart';
import 'state/session.dart';

final rootKey = GlobalKey<NavigatorState>();
final _shellKey = GlobalKey<NavigatorState>();

const _gateFree = {'/splash', '/offline', '/login', '/login/code', '/lock', '/gate', '/pin/setup', '/pin/bio'};

/// Where the app must be, given the session state (null = stay).
String? appRedirect(Session s, LockController lock, String loc) {
  switch (s.stage) {
    case Stage.booting:
      return loc == '/splash' ? null : '/splash';
    case Stage.offline:
      return loc == '/offline' ? null : '/offline';
    case Stage.signedOut:
      return loc.startsWith('/login') ? null : '/login';
    case Stage.ready:
      break;
  }
  if (s.offerPin) return loc.startsWith('/pin') ? null : '/pin/setup';
  if (lock.locked) return loc == '/lock' ? null : '/lock';
  if (s.needsRules) return loc == '/gate' ? null : '/gate';
  if (_gateFree.contains(loc)) {
    final next = s.pendingLink ?? '/home';
    s.pendingLink = null;
    return next;
  }
  return null;
}

/// Open a server link (push tap, notification row) now, or after unlock / rules acceptance.
void openLink(GoRouter router, Session s, LockController lock, String? link) {
  final route = mapServerLink(link);
  if (s.ready && !lock.locked && !s.needsRules && !s.offerPin) {
    router.push(route);
  } else {
    s.pendingLink = route;
  }
}

Page<void> _tab(Widget child) => NoTransitionPage(child: child);

GoRouter buildRouter(Session session, LockController lock) => GoRouter(
      navigatorKey: rootKey,
      initialLocation: '/splash',
      refreshListenable: Listenable.merge([session, lock]),
      redirect: (context, state) => appRedirect(session, lock, state.matchedLocation),
      routes: [
        GoRoute(path: '/splash', builder: (_, _) => const SplashScreen()),
        GoRoute(path: '/offline', builder: (_, _) => const OfflineScreen()),
        GoRoute(path: '/login', builder: (_, _) => const LoginPhoneScreen()),
        GoRoute(path: '/login/code', builder: (_, st) => LoginCodeScreen(phone: st.extra as String? ?? '')),
        GoRoute(path: '/pin/setup', builder: (_, _) => const PinSetupScreen()),
        GoRoute(path: '/pin/bio', builder: (_, _) => const BiometricOfferScreen()),
        GoRoute(path: '/pin/change', parentNavigatorKey: rootKey, builder: (_, _) => const PinSetupScreen(change: true)),
        GoRoute(path: '/lock', builder: (_, _) => const LockScreen()),
        GoRoute(path: '/gate', builder: (_, _) => const RulesGateScreen()),
        ShellRoute(
          navigatorKey: _shellKey,
          builder: (_, st, child) => AppShell(location: st.matchedLocation, child: child),
          routes: [
            GoRoute(path: '/home', pageBuilder: (_, st) => _tab(HomeScreen(childParam: int.tryParse(st.uri.queryParameters['child'] ?? '')))),
            GoRoute(path: '/schedule', pageBuilder: (_, _) => _tab(const ScheduleScreen())),
            GoRoute(path: '/homework', pageBuilder: (_, _) => _tab(const HomeworkListScreen())),
            GoRoute(path: '/chats', pageBuilder: (_, _) => _tab(const ChatsScreen())),
            GoRoute(path: '/coins', pageBuilder: (_, _) => _tab(const CoinsScreen())),
            GoRoute(path: '/payments', pageBuilder: (_, _) => _tab(const PaymentsScreen())),
            GoRoute(path: '/notifications', pageBuilder: (_, _) => _tab(const NotificationsScreen())),
            GoRoute(path: '/profile', pageBuilder: (_, _) => _tab(const ProfileScreen())),
          ],
        ),
        GoRoute(
            path: '/homework/:id',
            parentNavigatorKey: rootKey,
            builder: (_, st) => BlockedGate(child: HomeworkDetailScreen(id: int.parse(st.pathParameters['id']!)))),
        GoRoute(path: '/chats/new', parentNavigatorKey: rootKey, builder: (_, _) => const BlockedGate(child: NewChatScreen())),
        GoRoute(
            path: '/chats/:id',
            parentNavigatorKey: rootKey,
            builder: (_, st) => BlockedGate(child: ChatThreadScreen(id: int.parse(st.pathParameters['id']!)))),
        GoRoute(path: '/progress', parentNavigatorKey: rootKey, builder: (_, _) => const BlockedGate(child: ProgressScreen())),
        GoRoute(path: '/books', parentNavigatorKey: rootKey, builder: (_, _) => const BooksScreen()),
        GoRoute(path: '/orders', parentNavigatorKey: rootKey, builder: (_, _) => const OrdersScreen()),
        GoRoute(path: '/coins/history', parentNavigatorKey: rootKey, builder: (_, _) => const CoinHistoryScreen()),
        GoRoute(path: '/feedback', parentNavigatorKey: rootKey, builder: (_, _) => const FeedbackScreen()),
        GoRoute(path: '/rules', parentNavigatorKey: rootKey, builder: (_, st) => RulesScreen(tab: st.uri.queryParameters['tab'])),
        GoRoute(path: '/security', parentNavigatorKey: rootKey, builder: (_, _) => const SecurityScreen()),
      ],
    );
