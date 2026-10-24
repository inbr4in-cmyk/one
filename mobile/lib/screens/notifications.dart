import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:provider/provider.dart';

import '../api/models.dart';
import '../api/oe_api.dart';
import '../l10n/l10n.dart';
import '../push/links.dart';
import '../state/counters.dart';
import '../state/session.dart';
import '../state/settings.dart';
import '../ui/icons.dart';
import '../ui/theme.dart';
import '../ui/widgets.dart';
import '../util/format.dart';

enum NoticeFilter { all, attendance, payments, study }

NoticeFilter noticeGroup(String kind) {
  const att = {'absence', 'arrived', 'late', 'attendance', 'present'};
  const pay = {'payment', 'low_balance', 'debt', 'book_purchase', 'blocked', 'unblocked'};
  if (att.contains(kind)) return NoticeFilter.attendance;
  if (pay.contains(kind)) return NoticeFilter.payments;
  return NoticeFilter.study;
}

(String, Color Function(OeColors), Color Function(OeColors)) noticeStyle(String kind) => switch (noticeGroup(kind)) {
      NoticeFilter.attendance => kind == 'absence' || kind == 'late'
          ? ('clock', (o) => o.warn100, (o) => o.warn)
          : ('check', (o) => o.ok100, (o) => o.ok),
      NoticeFilter.payments => ('wallet', (o) => o.red100, (o) => o.red),
      _ => switch (kind) {
          'coins' || 'shop' => ('coin', (o) => o.coin100, (o) => o.coin),
          'complaint' => ('flag', (o) => o.navy100, (o) => o.tint),
          'lesson_cancelled' || 'lesson_moved' => ('cal', (o) => o.info100, (o) => o.info),
          _ => ('task', (o) => o.navy100, (o) => o.tint),
        },
    };

/// Screen 12 — the latest events first; each opens its screen.
class NotificationsScreen extends StatefulWidget {
  const NotificationsScreen({super.key});

  @override
  State<NotificationsScreen> createState() => _NotificationsScreenState();
}

class _NotificationsScreenState extends State<NotificationsScreen> {
  NoticeFilter _f = NoticeFilter.all;

  Future<List<Notice>> _load() async {
    final api = context.read<OeApi>();
    final counters = context.read<Counters>();
    final (unread, items) = await api.notifications();
    if (unread > 0) {
      // Opening the list reads it (as on the web); the dots stay for this visit.
      api.readAllNotifications().then((_) => counters.setNotificationsRead()).catchError((_) {});
    }
    return items;
  }

  @override
  Widget build(BuildContext context) {
    final t = context.t;
    final s = context.watch<Session>();
    final locale = context.watch<Settings>().locale;
    final body = Loader<List<Notice>>(
      load: _load,
      builder: (context, items, reload) {
        final shown = items.where((n) => _f == NoticeFilter.all || noticeGroup(n.kind) == _f).toList();
        final groups = <String, List<Notice>>{};
        for (final n in shown) {
          groups.putIfAbsent(_dayLabel(context, n.at, locale), () => []).add(n);
        }
        return PageList(onRefresh: reload, children: [
          SizedBox(
            height: 34,
            child: ListView(scrollDirection: Axis.horizontal, children: [
              for (final (f, l) in [
                (NoticeFilter.all, t.fAll),
                (NoticeFilter.attendance, t.fAttendance),
                (NoticeFilter.payments, t.fPayments),
                (NoticeFilter.study, t.fStudy),
              ])
                Padding(padding: const EdgeInsets.only(right: 8), child: OeChip(l, selected: _f == f, onTap: () => setState(() => _f = f))),
            ]),
          ),
          if (shown.isEmpty) EmptyState(icon: 'bell', title: t.noNotifications),
          for (final e in groups.entries) ...[
            Eyebrow(e.key),
            OeList(children: [for (final n in e.value) _NoticeRow(n: n)]),
          ],
        ]);
      },
    );
    if (s.isParent) {
      return Column(children: [TabHeader(t.navNotifications), Expanded(child: body)]);
    }
    return Column(children: [
      NavBar(backLabel: t.navHome, title: t.navNotifications),
      Expanded(child: body),
    ]);
  }

  String _dayLabel(BuildContext context, DateTime at, String locale) {
    final a = school(at), n = schoolNow();
    final days = DateTime.utc(n.year, n.month, n.day).difference(DateTime.utc(a.year, a.month, a.day)).inDays;
    if (days == 0) return context.t.today;
    if (days == 1) return context.t.yesterday;
    return dayMonth(at, locale);
  }
}

class _NoticeRow extends StatelessWidget {
  const _NoticeRow({required this.n});
  final Notice n;

  @override
  Widget build(BuildContext context) {
    final oe = context.oe;
    final (icon, bg, fg) = noticeStyle(n.kind);
    return InkWell(
      onTap: n.link == null ? null : () => context.push(mapServerLink(n.link)),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
        child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Container(
            width: 36,
            height: 36,
            alignment: Alignment.center,
            decoration: BoxDecoration(color: bg(oe), borderRadius: BorderRadius.circular(11)),
            child: OeIcon(icon, size: 20, color: fg(oe)),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(n.title, style: const TextStyle(fontWeight: FontWeight.w600)),
              if (n.body != null) Text(n.body!, style: TextStyle(fontSize: 13.5, color: oe.muted)),
              const SizedBox(height: 4),
              Text(hm(n.at), style: TextStyle(fontSize: 12, color: oe.muted)),
            ]),
          ),
          if (!n.read)
            Container(
                width: 8, height: 8, margin: const EdgeInsets.only(top: 6, left: 8), decoration: BoxDecoration(color: oe.red, shape: BoxShape.circle)),
        ]),
      ),
    );
  }
}
