import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:provider/provider.dart';

import '../api/models.dart';
import '../api/oe_api.dart';
import '../l10n/l10n.dart';
import '../push/links.dart';
import '../state/session.dart';
import '../state/settings.dart';
import '../ui/icons.dart';
import '../ui/theme.dart';
import '../ui/widgets.dart';
import '../util/format.dart';
import 'shell.dart';

class HomeData {
  HomeData({this.lessons = const [], this.homework, this.attendance, this.payments, this.coins, this.latest, this.consentMissing = false});
  final List<Lesson> lessons;
  final List<Homework>? homework;
  final Attendance? attendance;
  final Payments? payments;
  final CoinHistory? coins;
  final Notice? latest;
  final bool consentMissing;

  Lesson? get next {
    final now = DateTime.now();
    for (final l in lessons) {
      if (!l.cancelled && l.endsAt.isAfter(now)) return l;
    }
    return null;
  }

  /// Lessons in the last course payment, to show "5 of 12" (null when unknown).
  int? get packSize {
    final p = payments;
    if (p == null) return null;
    for (final i in p.items) {
      if (i.category == 'course' && i.lessons > 0) return i.lessons >= p.lessonsLeft && p.lessonsLeft >= 0 ? i.lessons : null;
    }
    return null;
  }
}

Future<T?> _soft<T>(Future<T> f) async {
  try {
    return await f;
  } catch (_) {
    return null;
  }
}

Future<HomeData> loadHome(OeApi api, Session s, {bool parent = false}) async {
  final c = s.child!;
  final today = dateOnly(schoolNow());
  final blocked = c.blocked;
  final monthStart = DateTime.utc(today.year, today.month, 1);
  final results = await Future.wait<Object?>([
    _soft(api.schedule(c.id, start: parent ? monthStart : today, days: parent ? 45 : 14)),
    blocked ? Future<Object?>.value(null) : _soft<Object?>(api.homework(c.id)),
    blocked ? Future<Object?>.value(null) : _soft<Object?>(api.attendance(c.id)),
    _soft(api.payments(c.id)),
    _soft(api.coins(c.id)),
    _soft(api.notifications()),
    _soft<DocVersion?>(api.document('recording')),
    _soft(api.myConsents()),
  ]);
  final rec = results[6] as DocVersion?;
  final consents = results[7] as List<MyConsent>?;
  final forId = s.isParent ? c.id : null;
  final missing = rec != null &&
      consents != null &&
      !consents.any((x) => x.documentId == rec.id && x.studentId == forId && x.revokedAt == null);
  final notes = results[5] as (int, List<Notice>)?;
  return HomeData(
    lessons: (results[0] as List<Lesson>?) ?? const [],
    homework: results[1] as List<Homework>?,
    attendance: results[2] as Attendance?,
    payments: results[3] as Payments?,
    coins: results[4] as CoinHistory?,
    latest: notes == null || notes.$2.isEmpty ? null : notes.$2.first,
    consentMissing: missing,
  );
}

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key, this.childParam});
  final int? childParam;

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  @override
  void initState() {
    super.initState();
    final p = widget.childParam;
    if (p != null) WidgetsBinding.instance.addPostFrameCallback((_) => context.read<Session>().selectChild(p));
    // Balances, coins and the blocked flag change after payments and orders.
    WidgetsBinding.instance.addPostFrameCallback((_) => context.read<Session>().reloadPortal());
  }

  @override
  Widget build(BuildContext context) {
    final s = context.watch<Session>();
    if (s.child == null) return const NoChild();
    return s.isParent ? const _ParentHome() : const _StudentHome();
  }
}

// ---------------------------------------------------------------- student (screen 2)

class _StudentHome extends StatelessWidget {
  const _StudentHome();

  @override
  Widget build(BuildContext context) {
    final s = context.watch<Session>();
    final api = context.read<OeApi>();
    final c = s.child!;
    return Loader<HomeData>(
      key: ValueKey('home-${c.id}-${c.blocked}'),
      skeletonLines: 5,
      load: () => loadHome(api, s),
      builder: (context, d, reload) {
        final t = context.t;
        final oe = context.oe;
        final locale = context.watch<Settings>().locale;
        final hw = (d.homework ?? const <Homework>[]).where((h) => h.status != 'checked').take(2).toList();
        return PageList(onRefresh: () async {
          await s.reloadPortal();
          await reload();
        }, children: [
          _Hello(line: todayLine(locale), hello: t.helloStudent(s.me!.fullName.split(' ').first)),
          ..._alerts(context, c, d),
          _NextLessonCard(lesson: d.next),
          Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Expanded(child: LessonsTile(left: c.lessonsLeft, pack: d.packSize)),
            const SizedBox(width: 12),
            Expanded(child: _CoinsTile(balance: d.coins?.balance ?? c.coins, week: d.coins?.earnedSince(DateTime.now().subtract(const Duration(days: 7))))),
          ]),
          if (!c.blocked)
            OeCard(
              padding: const EdgeInsets.fromLTRB(14, 14, 14, 4),
              child: Column(children: [
                SectionTitle(t.hwToday, action: t.allTasks, onAction: () => context.go('/homework'), padding: const EdgeInsets.only(bottom: 4)),
                if (hw.isEmpty)
                  Padding(padding: const EdgeInsets.symmetric(vertical: 12), child: Text(t.hwNone, style: TextStyle(color: oe.muted)))
                else
                  for (var i = 0; i < hw.length; i++) ...[
                    if (i > 0) Divider(height: 1, color: oe.line),
                    _HwLine(h: hw[i]),
                  ],
              ]),
            ),
          if (d.attendance != null && d.attendance!.monthRate != null) _AttendanceCard(a: d.attendance!, locale: locale),
          BranchCard(branch: c.branch),
        ]);
      },
    );
  }
}

List<Widget> _alerts(BuildContext context, Child c, HomeData d) {
  final t = context.t;
  return [
    if (c.blocked)
      Banner2(
        tone: Tone.red,
        icon: 'lock',
        title: t.blockedTitle,
        text: t.blockedText,
        action: OeButton(t.toPayments, small: true, expand: false, kind: BtnKind.red, onPressed: () => context.go('/payments')),
      )
    else if (c.debt)
      Banner2(tone: Tone.red, icon: 'wallet', title: t.debtTitle, text: t.debtText(-c.lessonsLeft), onTap: () => context.go('/payments'))
    else if (c.lessonsLeft > 0 && c.lessonsLeft <= 2)
      Banner2(tone: Tone.warn, icon: 'alert', title: t.lowTitle(c.lessonsLeft), text: t.lowText, onTap: () => context.go('/payments')),
    if (d.consentMissing)
      Banner2(icon: 'shield', title: t.consentTitle, text: t.consentText, onTap: () => context.push('/rules?tab=recording')),
  ];
}

class _Hello extends StatelessWidget {
  const _Hello({required this.line, required this.hello, this.bell = true});
  final String line;
  final String hello;
  final bool bell;

  @override
  Widget build(BuildContext context) {
    final oe = context.oe;
    return Padding(
      padding: const EdgeInsets.only(top: 6),
      child: Row(children: [
        Expanded(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(line, style: TextStyle(fontSize: 13, color: oe.muted)),
            Semantics(header: true, child: Text(hello, style: display(21, color: oe.brandInk, height: 1.2))),
          ]),
        ),
        if (bell) const BellAction(),
        avatarAction(context),
      ]),
    );
  }
}

class _NextLessonCard extends StatelessWidget {
  const _NextLessonCard({required this.lesson});
  final Lesson? lesson;

  String _until(BuildContext context, Duration d) {
    final t = context.t;
    if (d.isNegative) return t.lessonNow;
    if (d.inDays >= 1) return t.inDays(d.inDays);
    final h = d.inHours;
    final m = d.inMinutes % 60;
    return h > 0 ? t.inHoursMinutes(h, m) : t.inMinutes(m);
  }

  @override
  Widget build(BuildContext context) {
    final t = context.t;
    final oe = context.oe;
    final l = lesson;
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        gradient: LinearGradient(colors: [oe.hero, oe.hero2], begin: Alignment.topLeft, end: Alignment.bottomRight),
        borderRadius: BorderRadius.circular(OeStyle.cardRadius + 4),
      ),
      child: Stack(clipBehavior: Clip.none, children: [
        Positioned(
          right: -18,
          bottom: -26,
          child: Opacity(opacity: .1, child: OeIcon('grad', size: 130, color: OeColors.white)),
        ),
        Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [
            Expanded(
                child: Text(t.nextLesson.toUpperCase(),
                    style: TextStyle(fontSize: 12, letterSpacing: 1, color: oe.onHero2, fontWeight: FontWeight.w600))),
            if (l != null)
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                decoration: BoxDecoration(color: oe.red, borderRadius: BorderRadius.circular(999)),
                child: Text(_until(context, l.startsAt.difference(DateTime.now())),
                    style: const TextStyle(color: OeColors.white, fontSize: 12, fontWeight: FontWeight.w600)),
              ),
          ]),
          const SizedBox(height: 12),
          if (l == null)
            Text(t.noLessons, style: const TextStyle(color: OeColors.white, fontSize: 16, fontWeight: FontWeight.w500))
          else ...[
            Text.rich(TextSpan(children: [
              TextSpan(text: hm(l.startsAt), style: display(40, color: OeColors.white, height: 1)),
              TextSpan(text: '  – ${hm(l.endsAt)}', style: TextStyle(fontSize: 18, color: oe.onHero2, fontWeight: FontWeight.w500)),
            ])),
            const SizedBox(height: 10),
            Text(
                [
                  if (!_isToday(l.startsAt)) '${weekdayShort(l.startsAt, context.read<Settings>().locale)}, ${dayMonth(l.startsAt, context.read<Settings>().locale)}',
                  l.topic ?? l.group ?? t.individualLesson,
                ].join(' · '),
                style: const TextStyle(color: OeColors.white, fontSize: 14.5, fontWeight: FontWeight.w500)),
            const SizedBox(height: 10),
            Wrap(spacing: 6, runSpacing: 6, children: [
              if (l.room != null) _HeroMeta(icon: 'door', text: roomLabel(t, l.room!)),
              if (l.teacher != null) _HeroMeta(icon: 'user', text: l.teacher!),
            ]),
          ],
        ]),
      ]),
    );
  }
}

bool _isToday(DateTime d) {
  final a = school(d);
  final b = schoolNow();
  return a.year == b.year && a.month == b.month && a.day == b.day;
}

class _HeroMeta extends StatelessWidget {
  const _HeroMeta({required this.icon, required this.text});
  final String icon;
  final String text;

  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
        decoration: BoxDecoration(color: const Color(0x1FFFFFFF), borderRadius: BorderRadius.circular(999)),
        child: Row(mainAxisSize: MainAxisSize.min, children: [
          OeIcon(icon, size: 16, color: OeColors.white),
          const SizedBox(width: 6),
          Text(text, style: const TextStyle(color: OeColors.white, fontSize: 13, fontWeight: FontWeight.w500)),
        ]),
      );
}

/// "Осталось уроков 5 из 12" with segments (design 2 / 9).
class LessonsTile extends StatelessWidget {
  const LessonsTile({super.key, required this.left, this.pack});
  final int left;
  final int? pack;

  @override
  Widget build(BuildContext context) {
    final t = context.t;
    final oe = context.oe;
    final n = pack;
    return OeCard(
      onTap: () => context.go('/payments'),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(t.lessonsLeft, style: TextStyle(fontSize: 13, color: oe.muted, fontWeight: FontWeight.w500)),
        const SizedBox(height: 8),
        Text.rich(TextSpan(children: [
          TextSpan(text: '$left', style: display(30, color: left <= 0 ? oe.red : oe.ink, height: 1)),
          if (n != null) TextSpan(text: ' ${t.ofN(n)}', style: TextStyle(fontSize: 15, color: oe.muted, fontWeight: FontWeight.w600)),
        ])),
        const SizedBox(height: 10),
        if (n != null && n <= 12)
          Row(children: [
            for (var i = 0; i < n; i++)
              Expanded(
                child: Container(
                  height: 8,
                  margin: EdgeInsets.only(left: i == 0 ? 0 : 3),
                  decoration: BoxDecoration(
                      color: i >= n - left ? oe.primary : oe.fill, borderRadius: BorderRadius.circular(3)),
                ),
              ),
          ])
        else
          ClipRRect(
            borderRadius: BorderRadius.circular(4),
            child: LinearProgressIndicator(
                value: left <= 0 ? 0 : (n == null || n == 0 ? 1 : (left / n).clamp(0.0, 1.0)), minHeight: 8, backgroundColor: oe.fill, color: left <= 2 ? oe.warn : oe.primary),
          ),
        if (n != null) ...[
          const SizedBox(height: 8),
          Text(t.heldN(n - left), style: TextStyle(fontSize: 13, color: oe.muted)),
        ],
      ]),
    );
  }
}

class _CoinsTile extends StatelessWidget {
  const _CoinsTile({required this.balance, this.week});
  final int balance;
  final int? week;

  @override
  Widget build(BuildContext context) {
    final t = context.t;
    final oe = context.oe;
    return OeCard(
      onTap: () => context.go('/coins'),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(t.navCoins, style: TextStyle(fontSize: 13, color: oe.muted, fontWeight: FontWeight.w500)),
        const SizedBox(height: 8),
        Row(children: [
          const Coin(size: 20),
          const SizedBox(width: 6),
          Flexible(child: FittedBox(fit: BoxFit.scaleDown, child: Text(num(balance), style: display(30, color: oe.ink, height: 1)))),
        ]),
        const SizedBox(height: 10),
        if (week != null && week! > 0) Pill(t.perWeek(week!), tone: Tone.ok) else const SizedBox(height: 22),
      ]),
    );
  }
}

class _HwLine extends StatelessWidget {
  const _HwLine({required this.h});
  final Homework h;

  @override
  Widget build(BuildContext context) {
    final t = context.t;
    final oe = context.oe;
    final done = h.status != 'assigned';
    final now = DateTime.now();
    return InkWell(
      onTap: () => context.push('/homework/${h.id}'),
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 10),
        child: Row(children: [
          Container(
            width: 24,
            height: 24,
            decoration: BoxDecoration(
              color: done ? oe.ok : null,
              borderRadius: BorderRadius.circular(OeStyle.ios ? 7 : 4),
              border: Border.all(color: done ? oe.ok : oe.outline, width: 2),
            ),
            child: done ? const OeIcon('check', size: 16, color: OeColors.white, strokeWidth: 2.4) : null,
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(h.title, maxLines: 2, overflow: TextOverflow.ellipsis, style: const TextStyle(fontWeight: FontWeight.w600)),
              if (h.dueAt != null) Text(t.dueAt(hm(h.dueAt!)), style: TextStyle(fontSize: 12, color: oe.muted)),
            ]),
          ),
          hwPill(context, h, now),
        ]),
      ),
    );
  }
}

/// The coloured status mark of a homework (design 4a): deadline, review, grade.
Widget hwPill(BuildContext context, Homework h, DateTime now) {
  final t = context.t;
  if (h.status == 'checked') return Pill(h.grade != null ? t.hwCheckedGrade(h.grade!) : t.hwChecked, tone: Tone.ok);
  if (h.status == 'submitted') return Pill(t.hwSubmitted, tone: Tone.info);
  if (h.overdue(now)) return Pill(t.hwOverdue, tone: Tone.red);
  final due = h.dueAt;
  if (due != null && _isToday(due)) return Pill(t.hwTodayAt(hm(due)), tone: Tone.warn);
  if (due != null) return Pill(dayMonthShort(due, context.read<Settings>().locale), tone: Tone.mut);
  return Pill(t.hwAssigned, tone: Tone.mut);
}

class _AttendanceCard extends StatelessWidget {
  const _AttendanceCard({required this.a, required this.locale});
  final Attendance a;
  final String locale;

  @override
  Widget build(BuildContext context) {
    final t = context.t;
    final oe = context.oe;
    final rate = a.monthRate ?? 0;
    return OeCard(
      onTap: () => context.push('/progress'),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(crossAxisAlignment: CrossAxisAlignment.end, children: [
          Expanded(
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(t.attendanceMonth, style: TextStyle(fontSize: 13, color: oe.muted)),
              Text(monthName(DateTime.now(), locale), style: display(15, color: oe.brandInk)),
            ]),
          ),
          Text('$rate%', style: display(24, color: oe.ink)),
        ]),
        const SizedBox(height: 10),
        ClipRRect(
          borderRadius: BorderRadius.circular(4),
          child: LinearProgressIndicator(value: rate / 100, minHeight: 8, backgroundColor: oe.fill, color: oe.primary),
        ),
        const SizedBox(height: 8),
        Text(t.presentOf(a.monthPresent, a.monthLessons), style: TextStyle(fontSize: 13, color: oe.muted)),
      ]),
    );
  }
}

// ---------------------------------------------------------------- parent (screen 9)

class _ParentHome extends StatelessWidget {
  const _ParentHome();

  @override
  Widget build(BuildContext context) {
    final s = context.watch<Session>();
    final api = context.read<OeApi>();
    final c = s.child!;
    return Loader<HomeData>(
      key: ValueKey('phome-${c.id}-${c.blocked}'),
      skeletonLines: 5,
      load: () => loadHome(api, s, parent: true),
      builder: (context, d, reload) {
        final t = context.t;
        final oe = context.oe;
        final locale = context.watch<Settings>().locale;
        final now = DateTime.now();
        final month = (d.attendance?.items ?? const <Mark>[]).where((m) {
          final a = school(m.at), b = schoolNow();
          return a.year == b.year && a.month == b.month;
        }).toList();
        final grades = month.where((m) => m.grade != null).map((m) => m.grade!).toList();
        final avg = grades.isEmpty ? null : grades.reduce((a, b) => a + b) / grades.length;
        return PageList(onRefresh: () async {
          await s.reloadPortal();
          await reload();
        }, children: [
          _Hello(line: todayLine(locale), hello: t.helloParent(s.me!.fullName.split(' ').first), bell: false),
          const ChildSwitcher(cards: true),
          if (d.latest != null)
            Banner2(
              tone: Tone.ok,
              icon: 'check',
              title: d.latest!.title,
              text: [d.latest!.body, '${dayMonthShort(d.latest!.at, locale)}, ${hm(d.latest!.at)}'].whereType<String>().join(' · '),
              onTap: () => context.push(mapServerLink(d.latest!.link)),
            ),
          ..._alerts(context, c, d),
          Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Expanded(child: LessonsTile(left: c.lessonsLeft, pack: d.packSize)),
            const SizedBox(width: 12),
            Expanded(
              child: OeCard(
                onTap: () => context.push('/progress'),
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Text(t.avgGrade, style: TextStyle(fontSize: 13, color: oe.muted, fontWeight: FontWeight.w500)),
                  const SizedBox(height: 8),
                  Text(avg == null ? '—' : avg.toStringAsFixed(1).replaceAll('.', ','), style: display(30, color: oe.ink, height: 1)),
                  const SizedBox(height: 10),
                  Text(t.avgFor(monthName(now, locale), grades.length), style: TextStyle(fontSize: 13, color: oe.muted)),
                ]),
              ),
            ),
          ]),
          if (!c.blocked) _MonthCalendar(marks: month, lessons: d.lessons, locale: locale),
          if (!c.blocked)
            GridView.count(
              shrinkWrap: true,
              physics: const NeverScrollableScrollPhysics(),
              crossAxisCount: 4,
              crossAxisSpacing: 8,
              childAspectRatio: .9,
              children: [
                _QuickTile(icon: 'cal', label: t.navSchedule, onTap: () => context.go('/schedule')),
                _QuickTile(icon: 'task', label: t.navHomework, onTap: () => context.go('/homework')),
                _QuickTile(icon: 'chart', label: t.progress, onTap: () => context.push('/progress')),
                _QuickTile(icon: 'coin', label: t.navCoins, onTap: () => context.go('/coins')),
              ],
            ),
          BranchCard(branch: c.branch),
        ]);
      },
    );
  }
}

class _QuickTile extends StatelessWidget {
  const _QuickTile({required this.icon, required this.label, required this.onTap});
  final String icon;
  final String label;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) => OeCard(
        onTap: onTap,
        padding: const EdgeInsets.symmetric(vertical: 10, horizontal: 4),
        child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
          IconTile(icon, size: 36),
          const SizedBox(height: 6),
          Text(label, maxLines: 1, overflow: TextOverflow.ellipsis, style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w500)),
        ]),
      );
}

/// Attendance calendar for the month: present, late, absent, upcoming.
class _MonthCalendar extends StatelessWidget {
  const _MonthCalendar({required this.marks, required this.lessons, required this.locale});
  final List<Mark> marks;
  final List<Lesson> lessons;
  final String locale;

  @override
  Widget build(BuildContext context) {
    final t = context.t;
    final oe = context.oe;
    final now = schoolNow();
    final first = DateTime.utc(now.year, now.month, 1);
    final days = DateTime.utc(now.year, now.month + 1, 0).day;
    final byDay = <int, String>{};
    for (final m in marks) {
      final d = school(m.at).day;
      final prev = byDay[d];
      // The worst status of the day wins.
      const rank = {'present': 0, 'excused': 1, 'late': 2, 'absent': 3};
      if (prev == null || (rank[m.status] ?? 0) > (rank[prev] ?? 0)) byDay[d] = m.status;
    }
    for (final l in lessons) {
      final s = school(l.startsAt);
      if (s.month == now.month && s.year == now.year && !l.cancelled && l.startsAt.isAfter(DateTime.now())) {
        byDay.putIfAbsent(s.day, () => 'future');
      }
    }
    final present = marks.where((m) => m.attended).length;
    final lead = (first.weekday + 6) % 7;
    Color? dot(String? st) => switch (st) {
          'present' => oe.ok,
          'excused' => oe.info,
          'late' => oe.warn,
          'absent' => oe.red,
          'future' => oe.line,
          _ => null,
        };
    final week = [t.wdMon, t.wdTue, t.wdWed, t.wdThu, t.wdFri, t.wdSat, t.wdSun];
    return OeCard(
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Expanded(child: Text(t.attendanceOf(monthName(DateTime.now(), locale)), style: display(15, color: oe.brandInk))),
          Text(t.nOfM(present, marks.length), style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600)),
        ]),
        const SizedBox(height: 12),
        Table(children: [
          TableRow(children: [
            for (final w in week)
              Center(child: Text(w, style: TextStyle(fontSize: 11, color: oe.muted, fontWeight: FontWeight.w600))),
          ]),
          for (var r = 0; r * 7 < lead + days; r++)
            TableRow(children: [
              for (var c = 0; c < 7; c++)
                Builder(builder: (_) {
                  final day = r * 7 + c - lead + 1;
                  if (day < 1 || day > days) return const SizedBox(height: 34);
                  final st = byDay[day];
                  final today = day == now.day;
                  return Container(
                    height: 34,
                    margin: const EdgeInsets.all(1),
                    decoration: BoxDecoration(color: today ? oe.navy100 : null, borderRadius: BorderRadius.circular(8)),
                    child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
                      Text('$day',
                          style: TextStyle(
                              fontSize: 12,
                              fontWeight: st != null ? FontWeight.w600 : FontWeight.w400,
                              color: st != null ? oe.ink : oe.muted)),
                      const SizedBox(height: 2),
                      Container(width: 5, height: 5, decoration: BoxDecoration(color: dot(st), shape: BoxShape.circle)),
                    ]),
                  );
                }),
            ]),
        ]),
        const SizedBox(height: 10),
        Wrap(spacing: 12, runSpacing: 4, children: [
          for (final (c, l) in [(oe.ok, t.stPresent), (oe.warn, t.stLate), (oe.red, t.stAbsent), (oe.line, t.stAhead)])
            Row(mainAxisSize: MainAxisSize.min, children: [
              Container(width: 8, height: 8, decoration: BoxDecoration(color: c, shape: BoxShape.circle)),
              const SizedBox(width: 5),
              Text(l, style: TextStyle(fontSize: 12, color: oe.muted)),
            ]),
        ]),
      ]),
    );
  }
}
