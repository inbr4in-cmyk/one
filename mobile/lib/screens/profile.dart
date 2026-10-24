import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:provider/provider.dart';

import '../api/models.dart';
import '../api/oe_api.dart';
import '../l10n/l10n.dart';
import '../state/lock.dart';
import '../state/session.dart';
import '../state/settings.dart';
import '../ui/icons.dart';
import '../ui/theme.dart';
import '../ui/widgets.dart';
import '../util/format.dart';

/// Screen 8 — who I am, lessons and coins, the pages that don't fit the tab bar, language, theme, security, sign out.
class ProfileScreen extends StatelessWidget {
  const ProfileScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final t = context.t;
    final oe = context.oe;
    final s = context.watch<Session>();
    final settings = context.watch<Settings>();
    final me = s.me;
    if (me == null) return const SizedBox();
    final c = s.child;
    final canPop = context.canPop();
    Widget link(String icon, String title, String route, {String? subtitle, Color? bg, Color? fg}) => OeRow(
          leading: IconTile(icon, bg: bg, fg: fg),
          title: title,
          subtitle: subtitle,
          chevron: true,
          onTap: () => context.push(route),
        );
    return Column(children: [
      if (canPop) NavBar(backLabel: t.navHome) else TabHeader(t.navProfile),
      Expanded(
        child: PageList(children: [
          Column(children: [
            Avatar(me.fullName, size: 80, tone: 0),
            const SizedBox(height: 10),
            Text(me.fullName, textAlign: TextAlign.center, style: display(21, color: oe.brandInk)),
            const SizedBox(height: 4),
            Text(
                s.isParent
                    ? '${t.roleParent} · ${formatPhone(me.phone)}'
                    : [c?.level, c?.mainGroup?.name, c?.branch.name].whereType<String>().join(' · '),
                textAlign: TextAlign.center,
                style: TextStyle(fontSize: 13, color: oe.muted)),
          ]),
          if (!s.isParent && c != null)
            OeCard(
              padding: const EdgeInsets.symmetric(vertical: 12),
              child: Row(children: [
                _Trio(value: '${c.lessonsLeft}', label: t.trioLeft, color: c.lessonsLeft <= 0 ? oe.red : oe.tint),
                Container(width: 1, height: 36, color: oe.line),
                _Trio(value: num(c.coins), label: t.trioCoins),
                Container(width: 1, height: 36, color: oe.line),
                _Trio(value: '${c.stars}', label: t.trioStars),
              ]),
            ),
          if (s.isParent && s.children.isNotEmpty)
            OeList(children: [
              for (final k in s.children)
                OeRow(
                  leading: Avatar(k.fullName, size: 36),
                  title: k.fullName,
                  titleStyle: const TextStyle(fontWeight: FontWeight.w600),
                  subtitle: [k.mainGroup?.name, t.lessonsN(k.lessonsLeft)].whereType<String>().join(' · '),
                  trailing: k.id == c?.id ? Pill(t.selected, tone: Tone.info) : null,
                  onTap: () => s.selectChild(k.id),
                ),
            ]),
          OeList(children: [
            link('chart', t.progressAndGrades, '/progress'),
            link('book', t.myBooks, '/books', subtitle: c?.level, bg: oe.ok100, fg: oe.ok),
            if (!s.isParent) link('wallet', t.navPayments, '/payments'),
            if (!s.isParent) link('bell', t.navNotifications, '/notifications'),
            link('flag', t.feedback, '/feedback', bg: oe.warn100, fg: oe.warn),
            link('file', t.rulesTitle, '/rules'),
          ]),
          OeList(children: [
            OeRow(
              leading: const IconTile('globe'),
              title: t.language,
              trailing: SizedBox(
                width: 150,
                child: OeSegmented<String>(
                  value: settings.locale,
                  onChanged: (v) => settings.locale = v,
                  options: const [('ru', 'Рус'), ('kk', 'Қаз')],
                ),
              ),
            ),
            OeRow(
              leading: const IconTile('gear'),
              title: t.theme,
              trailing: SizedBox(
                width: 190,
                child: OeSegmented<ThemeMode>(
                  value: settings.theme,
                  onChanged: (v) => settings.theme = v,
                  options: [(ThemeMode.light, t.themeLight), (ThemeMode.dark, t.themeDark), (ThemeMode.system, t.themeSystem)],
                ),
              ),
            ),
            link('shield', t.security, '/security', subtitle: t.securitySub, bg: oe.ok100, fg: oe.ok),
            link('headset', t.writeManager, '/chats/new'),
          ]),
          OeButton(t.logout, key: const Key('logout'), kind: BtnKind.ghost, icon: 'logout', onPressed: () async {
            if (await confirm(context, title: t.logoutTitle, text: t.logoutText, ok: t.logout, danger: true)) {
              if (context.mounted) await context.read<Session>().signOut();
            }
          }),
          Center(child: Text('One English · v1.0.0', style: TextStyle(fontSize: 12, color: oe.muted))),
        ]),
      ),
    ]);
  }
}

class _Trio extends StatelessWidget {
  const _Trio({required this.value, required this.label, this.color});
  final String value;
  final String label;
  final Color? color;

  @override
  Widget build(BuildContext context) => Expanded(
        child: Column(children: [
          Text(value, style: display(22, color: color ?? context.oe.ink)),
          const SizedBox(height: 2),
          Text(label, style: TextStyle(fontSize: 12, color: context.oe.muted)),
        ]),
      );
}

/// Screen 14 — biometrics, PIN, auto-lock, active devices (end one or all others).
class SecurityScreen extends StatefulWidget {
  const SecurityScreen({super.key});

  @override
  State<SecurityScreen> createState() => _SecurityScreenState();
}

class _SecurityScreenState extends State<SecurityScreen> {
  bool _bioAvailable = false;

  @override
  void initState() {
    super.initState();
    context.read<LockController>().biometricsAvailable().then((v) {
      if (mounted) setState(() => _bioAvailable = v);
    });
  }

  @override
  Widget build(BuildContext context) {
    final t = context.t;
    final oe = context.oe;
    final lock = context.watch<LockController>();
    final settings = context.watch<Settings>();
    final ios = OeStyle.ios;
    return Scaffold(
      appBar: NavBar(backLabel: t.navProfile, title: t.security),
      body: Loader<List<SessionInfo>>(
        load: () => context.read<OeApi>().sessions(),
        builder: (context, sessions, reload) => PageList(onRefresh: reload, children: [
          OeList(children: [
            if (lock.pinSet && _bioAvailable)
              OeRow(
                leading: IconTile(ios ? 'faceid' : 'finger', bg: oe.fill, fg: oe.ink),
                title: ios ? t.bioToggleIos : t.bioToggleAndroid,
                trailing: OeSwitch(
                  value: settings.biometrics,
                  onChanged: (v) async {
                    if (v && !await lock.authenticate(t.bioReason)) return;
                    settings.biometrics = v;
                  },
                ),
              ),
            OeRow(
              leading: IconTile('key', bg: oe.fill, fg: oe.ink),
              title: lock.pinSet ? t.pinChange : t.pinSet,
              chevron: true,
              onTap: () => context.push('/pin/change'),
            ),
            if (lock.pinSet)
              Padding(
                padding: const EdgeInsets.fromLTRB(14, 12, 14, 14),
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Row(children: [
                    IconTile('lock', bg: oe.fill, fg: oe.ink),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                        Text(t.autolock, style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w500)),
                        Text(t.autolockText, style: TextStyle(fontSize: 12.5, color: oe.muted)),
                      ]),
                    ),
                  ]),
                  const SizedBox(height: 10),
                  OeSegmented<int>(
                    value: settings.autolockMinutes,
                    onChanged: (v) => settings.autolockMinutes = v,
                    options: [(0, t.autolockNow), (1, t.minutesN(1)), (5, t.minutesN(5)), (15, t.minutesN(15))],
                  ),
                ]),
              ),
            if (lock.pinSet)
              OeRow(
                leading: IconTile('x', bg: oe.fill, fg: oe.ink),
                title: t.pinOff,
                onTap: () async {
                  if (await confirm(context, title: t.pinOffTitle, text: t.pinOffText, ok: t.pinOff, danger: true)) {
                    await lock.clear();
                    settings.biometrics = false;
                  }
                },
              ),
          ]),
          SectionTitle(t.devices, padding: const EdgeInsets.only(top: 6)),
          OeList(children: [
            for (final d in sessions)
              OeRow(
                leading: IconTile(_isPhone(d.userAgent) ? 'phone' : 'monitor', bg: oe.fill, fg: oe.ink),
                title: _deviceName(context, d.userAgent),
                titleStyle: const TextStyle(fontWeight: FontWeight.w600, fontSize: 14),
                subtitle: [if (d.ip != null) d.ip!, if (d.lastUsedAt != null) '${dmy(d.lastUsedAt!)} ${hm(d.lastUsedAt!)}'].join(' · '),
                trailing: d.current
                    ? Pill(t.thisDevice, tone: Tone.ok)
                    : OeButton(t.endSession, small: true, expand: false, kind: BtnKind.tonal, onPressed: () async {
                        try {
                          await context.read<OeApi>().endSession(d.id);
                          await reload();
                        } catch (e) {
                          if (context.mounted) toastError(context, e);
                        }
                      }),
              ),
          ]),
          if (sessions.where((x) => !x.current).isNotEmpty)
            OeButton(t.endOthers, kind: BtnKind.ghost, onPressed: () async {
              if (!await confirm(context, title: t.endOthers, text: t.endOthersText, ok: t.endSession, danger: true)) return;
              if (!context.mounted) return;
              try {
                await context.read<OeApi>().endOtherSessions();
                await reload();
              } catch (e) {
                if (context.mounted) toastError(context, e);
              }
            }),
          Text(t.devicesHint, textAlign: TextAlign.center, style: TextStyle(fontSize: 12, color: oe.muted)),
        ]),
      ),
    );
  }

  bool _isPhone(String? ua) => ua != null && RegExp(r'android|iphone|ipad|dart|okhttp|mobile', caseSensitive: false).hasMatch(ua);

  String _deviceName(BuildContext context, String? ua) {
    if (ua == null || ua.isEmpty) return context.t.unknownDevice;
    final u = ua.toLowerCase();
    if (u.contains('iphone')) return 'iPhone';
    if (u.contains('ipad')) return 'iPad';
    if (u.contains('android')) return 'Android';
    if (u.contains('dart')) return context.t.appDevice;
    final browser = u.contains('edg/') ? 'Edge' : u.contains('chrome') ? 'Chrome' : u.contains('firefox') ? 'Firefox' : u.contains('safari') ? 'Safari' : '';
    final os = u.contains('windows') ? 'Windows' : u.contains('mac os') ? 'macOS' : u.contains('linux') ? 'Linux' : '';
    final s = [if (browser.isNotEmpty) browser, if (os.isNotEmpty) os].join(', ');
    return s.isEmpty ? ua.split(' ').first : '${context.t.web} · $s';
  }
}

/// Settings icon for headers.
Widget gearIcon(BuildContext context) => OeIcon('gear', color: context.oe.tint);
