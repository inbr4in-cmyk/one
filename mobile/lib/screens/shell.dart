import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';

import '../api/models.dart';
import '../l10n/l10n.dart';
import '../state/counters.dart';
import '../state/session.dart';
import '../ui/icons.dart';
import '../ui/theme.dart';
import '../ui/widgets.dart';

class _Tab {
  const _Tab(this.path, this.icon, this.label, {this.badge = 0, this.dot = false});
  final String path;
  final String icon;
  final String label;
  final int badge;
  final bool dot;
}

/// Pages open while the child's access is paused for non-payment (server: «Доступ приостановлен до оплаты»).
const openWhenBlocked = {'/home', '/payments', '/profile', '/notifications'};

/// Bottom navigation: students — home, schedule, homework, chats, coins; parents — home, payments, chats, notifications, profile.
class AppShell extends StatelessWidget {
  const AppShell({super.key, required this.location, required this.child});
  final String location;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    final t = context.t;
    final s = context.watch<Session>();
    final c = context.watch<Counters>();
    final tabs = s.isParent
        ? [
            _Tab('/home', 'home', t.navHome),
            _Tab('/payments', 'wallet', t.navPayments, dot: s.children.any((k) => k.debt || k.blocked)),
            _Tab('/chats', 'chat', t.navChats, badge: c.chats),
            _Tab('/notifications', 'bell', t.navNotifications, badge: c.notifications),
            _Tab('/profile', 'user', t.navProfile),
          ]
        : [
            _Tab('/home', 'home', t.navHome),
            _Tab('/schedule', 'cal', t.navSchedule),
            _Tab('/homework', 'task', t.navHomework, badge: c.homework),
            _Tab('/chats', 'chat', t.navChats, badge: c.chats),
            _Tab('/coins', 'coin', t.navCoins),
          ];
    final blocked = (s.child?.blocked ?? false) && !openWhenBlocked.contains(location);
    return Scaffold(
      body: SafeArea(bottom: false, child: blocked ? const BlockedView() : child),
      bottomNavigationBar: _TabBar(tabs: tabs, current: location),
    );
  }
}

class _TabBar extends StatelessWidget {
  const _TabBar({required this.tabs, required this.current});
  final List<_Tab> tabs;
  final String current;

  @override
  Widget build(BuildContext context) {
    final oe = context.oe;
    final ios = OeStyle.ios;
    return Container(
      decoration: BoxDecoration(
        color: ios ? oe.surface : oe.m3nav,
        border: ios ? Border(top: BorderSide(color: oe.line)) : null,
      ),
      child: SafeArea(
        top: false,
        child: SizedBox(
          height: ios ? 50 : 80,
          child: Row(children: [
            for (final tab in tabs) Expanded(child: _TabItem(tab: tab, active: tab.path == current)),
          ]),
        ),
      ),
    );
  }
}

class _TabItem extends StatelessWidget {
  const _TabItem({required this.tab, required this.active});
  final _Tab tab;
  final bool active;

  @override
  Widget build(BuildContext context) {
    final oe = context.oe;
    final ios = OeStyle.ios;
    final color = active ? (ios ? oe.tint : oe.ink) : oe.muted;
    Widget icon = OeIcon(tab.icon, color: color, duo: active ? (ios ? .18 : .22) : 0);
    if (!ios) {
      icon = AnimatedContainer(
        duration: context.motion(200),
        width: 64,
        height: 32,
        alignment: Alignment.center,
        decoration: BoxDecoration(color: active ? oe.navy100 : Colors.transparent, borderRadius: BorderRadius.circular(16)),
        child: icon,
      );
    }
    final badge = tab.badge > 0
        ? Positioned(
            top: ios ? -4 : 0,
            left: ios ? 15 : 34,
            child: Container(
              decoration: BoxDecoration(
                  borderRadius: BorderRadius.circular(9), border: ios ? Border.all(color: oe.surface, width: 2) : null),
              child: CountBadge(tab.badge, size: 18),
            ),
          )
        : tab.dot
            ? Positioned(
                top: ios ? -1 : 3,
                left: ios ? 17 : 38,
                child: Container(width: 10, height: 10, decoration: BoxDecoration(color: oe.red, shape: BoxShape.circle)),
              )
            : null;
    return Semantics(
      button: true,
      selected: active,
      label: tab.badge > 0 ? '${tab.label}, ${tab.badge}' : tab.label,
      excludeSemantics: true,
      child: InkResponse(
        key: Key('tab${tab.path}'),
        onTap: () => context.go(tab.path),
        highlightShape: BoxShape.rectangle,
        child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
          Stack(clipBehavior: Clip.none, children: [icon, ?badge]),
          SizedBox(height: ios ? 3 : 4),
          Text(tab.label,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                  fontSize: ios ? 10.5 : 12,
                  fontWeight: active && !ios ? FontWeight.w600 : FontWeight.w500,
                  color: color)),
        ]),
      ),
    );
  }
}

/// Lock screen for pages closed while access is paused: what to do and whom to call.
class BlockedView extends StatelessWidget {
  const BlockedView({super.key});

  @override
  Widget build(BuildContext context) {
    final t = context.t;
    final child = context.watch<Session>().child;
    return ListView(padding: const EdgeInsets.all(16), children: [
      const SizedBox(height: 24),
      EmptyState(
        icon: 'lock',
        title: t.blockedTitle,
        text: t.blockedText,
        action: OeButton(t.toPayments, kind: BtnKind.red, onPressed: () => context.go('/payments')),
      ),
      if (child != null) BranchCard(branch: child.branch),
    ]);
  }
}

/// Wraps detail pages outside the tab shell.
class BlockedGate extends StatelessWidget {
  const BlockedGate({super.key, required this.child});
  final Widget child;

  @override
  Widget build(BuildContext context) {
    final blocked = context.watch<Session>().child?.blocked ?? false;
    if (!blocked) return child;
    return Scaffold(appBar: NavBar(backLabel: context.t.back), body: const BlockedView());
  }
}

class BranchCard extends StatelessWidget {
  const BranchCard({super.key, required this.branch});
  final Branch branch;

  @override
  Widget build(BuildContext context) {
    final oe = context.oe;
    final phone = branch.phone;
    return OeCard(
      child: Row(children: [
        IconTile('pin', bg: oe.navy100),
        const SizedBox(width: 12),
        Expanded(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(context.t.branchName(branch.name), style: const TextStyle(fontWeight: FontWeight.w600)),
            if (branch.address != null) Text(branch.address!, style: TextStyle(fontSize: 13, color: oe.muted)),
          ]),
        ),
        if (phone != null)
          OeButton(context.t.call,
              small: true,
              expand: false,
              kind: BtnKind.tonal,
              icon: 'phone',
              onPressed: () => launchUrl(Uri.parse('tel:${phone.replaceAll(' ', '')}'))),
      ]),
    );
  }
}

/// Parent's child switcher: cards on the home screen, compact chips elsewhere. Keeps the context for all tabs.
class ChildSwitcher extends StatelessWidget {
  const ChildSwitcher({super.key, this.cards = false});
  final bool cards;

  @override
  Widget build(BuildContext context) {
    final s = context.watch<Session>();
    final kids = s.children;
    if (!s.isParent || kids.length < 2) return const SizedBox.shrink();
    final oe = context.oe;
    final cur = s.child?.id;
    if (!cards) {
      return SizedBox(
        height: 36,
        child: ListView.separated(
          scrollDirection: Axis.horizontal,
          padding: const EdgeInsets.symmetric(horizontal: 16),
          itemCount: kids.length,
          separatorBuilder: (_, _) => const SizedBox(width: 8),
          itemBuilder: (_, i) => OeChip(kids[i].firstName, selected: kids[i].id == cur, onTap: () => s.selectChild(kids[i].id)),
        ),
      );
    }
    return Row(children: [
      for (var i = 0; i < kids.length && i < 3; i++) ...[
        if (i > 0) const SizedBox(width: 8),
        Expanded(
          child: Semantics(
            selected: kids[i].id == cur,
            button: true,
            child: GestureDetector(
              key: Key('kid-${kids[i].id}'),
              onTap: () => s.selectChild(kids[i].id),
              child: AnimatedContainer(
                duration: context.motion(150),
                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
                decoration: BoxDecoration(
                  color: oe.surface,
                  borderRadius: BorderRadius.circular(OeStyle.cardRadius),
                  border: Border.all(color: kids[i].id == cur ? oe.primary : oe.line, width: kids[i].id == cur ? 2 : 1),
                ),
                child: Row(children: [
                  Stack(clipBehavior: Clip.none, children: [
                    Avatar(kids[i].fullName, size: 36),
                    if (kids[i].debt || kids[i].blocked)
                      Positioned(
                          right: -2,
                          top: -2,
                          child: Container(
                              width: 10, height: 10, decoration: BoxDecoration(color: oe.red, shape: BoxShape.circle))),
                  ]),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                      Text(kids[i].firstName, maxLines: 1, overflow: TextOverflow.ellipsis,
                          style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 14)),
                      Text(kids[i].mainGroup?.name ?? kids[i].level ?? '',
                          maxLines: 1, overflow: TextOverflow.ellipsis, style: TextStyle(fontSize: 12, color: oe.muted)),
                    ]),
                  ),
                ]),
              ),
            ),
          ),
        ),
      ],
    ]);
  }
}

/// Header icon that opens the notifications list (students; parents have a tab).
class BellAction extends StatelessWidget {
  const BellAction({super.key});

  @override
  Widget build(BuildContext context) => HeaderAction('bell',
      label: context.t.navNotifications,
      badge: context.watch<Counters>().notifications,
      onTap: () => context.push('/notifications'));
}

/// Shared “no child linked” state.
class NoChild extends StatelessWidget {
  const NoChild({super.key});

  @override
  Widget build(BuildContext context) =>
      EmptyState(icon: 'users', title: context.t.noChildren, text: context.t.noChildrenText);
}

/// Header icon used by child-scoped pages.
Widget avatarAction(BuildContext context) {
  final name = context.watch<Session>().me?.fullName ?? '';
  return Semantics(
    button: true,
    label: context.t.navProfile,
    child: GestureDetector(
      onTap: () => context.push('/profile'),
      child: Padding(padding: const EdgeInsets.symmetric(horizontal: 6), child: Avatar(name, size: 40, tone: 0)),
    ),
  );
}

/// Icon used in several lists for a lesson status.
String attendanceIcon(String status) => switch (status) {
      'present' => 'check',
      'late' => 'clock',
      'absent' => 'x',
      _ => 'alert',
    };

/// Tile icon (`OeIcon`) for headers.
Widget brandTile(BuildContext context) => const OeLogoMark(width: 34);
