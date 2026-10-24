import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../api/models.dart';
import '../api/oe_api.dart';
import '../l10n/l10n.dart';
import '../state/session.dart';
import '../state/settings.dart';
import '../ui/icons.dart';
import '../ui/theme.dart';
import '../ui/widgets.dart';
import '../util/format.dart';
import 'shell.dart';

DateTime weekStart(DateTime schoolDay) {
  final d = dateOnly(schoolDay);
  return d.subtract(Duration(days: d.weekday - 1));
}

bool sameDay(DateTime a, DateTime b) => a.year == b.year && a.month == b.month && a.day == b.day;

/// Screen 3 — the week with lesson dots, cancellations as a banner, attendance and a 1–5 rating of past lessons.
class ScheduleScreen extends StatefulWidget {
  const ScheduleScreen({super.key});

  @override
  State<ScheduleScreen> createState() => _ScheduleScreenState();
}

class _ScheduleScreenState extends State<ScheduleScreen> {
  DateTime _week = weekStart(schoolNow());

  @override
  Widget build(BuildContext context) {
    final t = context.t;
    final s = context.watch<Session>();
    final c = s.child;
    final locale = context.watch<Settings>().locale;
    final end = _week.add(const Duration(days: 6));
    return Column(children: [
      TabHeader(t.navSchedule, actions: [
        HeaderAction('cal', label: t.thisWeek, onTap: () => setState(() => _week = weekStart(schoolNow()))),
        if (!s.isParent) avatarAction(context),
      ]),
      const ChildSwitcher(),
      if (c == null)
        const Expanded(child: NoChild())
      else
        Expanded(
          child: Column(children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 8, 8, 4),
              child: Row(children: [
                Expanded(
                  child: Text('${end.month == _week.month ? '${_week.day}' : dayMonth(_week, locale)} – ${dayMonth(end, locale)}',
                      style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 15)),
                ),
                IconButton(
                    tooltip: t.prevWeek,
                    onPressed: () => setState(() => _week = _week.subtract(const Duration(days: 7))),
                    icon: OeIcon('chev-l', color: context.oe.tint)),
                IconButton(
                    tooltip: t.nextWeek,
                    onPressed: () => setState(() => _week = _week.add(const Duration(days: 7))),
                    icon: OeIcon('chev-r', color: context.oe.tint)),
              ]),
            ),
            Expanded(
              child: Loader<(List<Lesson>, Attendance?)>(
                key: ValueKey('sch-${c.id}-$_week'),
                load: () async {
                  final api = context.read<OeApi>();
                  final r = await Future.wait<Object?>([
                    api.schedule(c.id, start: _week, days: 7),
                    c.blocked ? Future.value(null) : api.attendance(c.id).then<Attendance?>((a) => a).catchError((_) => null),
                  ]);
                  return (r[0] as List<Lesson>, r[1] as Attendance?);
                },
                builder: (context, d, reload) => _Week(week: _week, lessons: d.$1, attendance: d.$2, child: c, reload: reload),
              ),
            ),
          ]),
        ),
    ]);
  }
}

class _Week extends StatelessWidget {
  const _Week({required this.week, required this.lessons, required this.attendance, required this.child, required this.reload});
  final DateTime week;
  final List<Lesson> lessons;
  final Attendance? attendance;
  final Child child;
  final Future<void> Function() reload;

  @override
  Widget build(BuildContext context) {
    final t = context.t;
    final oe = context.oe;
    final locale = context.watch<Settings>().locale;
    final today = dateOnly(schoolNow());
    final marks = {for (final m in attendance?.items ?? const <Mark>[]) m.lessonId: m};
    final byDay = <DateTime, List<Lesson>>{};
    for (final l in lessons) {
      byDay.putIfAbsent(dateOnly(school(l.startsAt)), () => []).add(l);
    }
    final upcoming = byDay.keys.where((d) => !d.isBefore(today)).toList()..sort();
    final past = byDay.keys.where((d) => d.isBefore(today)).toList()..sort((a, b) => b.compareTo(a));
    final order = [...upcoming, ...past];
    final cancelled = lessons.where((l) => l.cancelled).toList();
    return PageList(onRefresh: reload, padding: const EdgeInsets.fromLTRB(16, 0, 16, 24), children: [
      Row(children: [
        for (var i = 0; i < 7; i++)
          Expanded(
            child: Builder(builder: (_) {
              final d = week.add(Duration(days: i));
              final isToday = sameDay(d, today);
              final has = byDay.containsKey(d);
              return Container(
                margin: const EdgeInsets.symmetric(horizontal: 2),
                padding: const EdgeInsets.symmetric(vertical: 8),
                decoration: BoxDecoration(color: isToday ? oe.primary : null, borderRadius: BorderRadius.circular(14)),
                child: Column(children: [
                  Text(weekdayShort(d.subtract(const Duration(hours: 5)), locale),
                      style: TextStyle(fontSize: 12, color: isToday ? oe.onHero2 : oe.muted)),
                  const SizedBox(height: 4),
                  Text('${d.day}',
                      style: TextStyle(fontSize: 17, fontWeight: FontWeight.w600, color: isToday ? oe.onPrimary : oe.ink)),
                  const SizedBox(height: 4),
                  Container(
                      width: 5,
                      height: 5,
                      decoration: BoxDecoration(
                          color: has ? (isToday ? oe.onPrimary : oe.tint) : Colors.transparent, shape: BoxShape.circle)),
                ]),
              );
            }),
          ),
      ]),
      for (final l in cancelled)
        Banner2(
          icon: 'alert',
          tone: Tone.info,
          title: t.cancelledOn('${weekdayLong(l.startsAt, locale)}, ${dayMonth(l.startsAt, locale)}', hm(l.startsAt)),
          text: l.cancelReason,
        ),
      if (order.isEmpty) EmptyState(icon: 'cal', title: t.noLessonsWeek),
      for (final d in order)
        Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          SizedBox(
            width: 48,
            child: Padding(
              padding: const EdgeInsets.only(top: 12),
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text(weekdayShort(d.subtract(const Duration(hours: 5)), locale), style: TextStyle(fontSize: 12, color: oe.muted)),
                Text('${d.day}', style: display(17, color: oe.ink)),
              ]),
            ),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Column(children: [
              for (final l in byDay[d]!) ...[
                LessonCard(lesson: l, mark: marks[l.id], studentId: child.id, today: sameDay(d, today)),
                const SizedBox(height: 10),
              ],
            ]),
          ),
        ]),
    ]);
  }
}

class LessonCard extends StatefulWidget {
  const LessonCard({super.key, required this.lesson, required this.mark, required this.studentId, required this.today});
  final Lesson lesson;
  final Mark? mark;
  final int studentId;
  final bool today;

  @override
  State<LessonCard> createState() => _LessonCardState();
}

class _LessonCardState extends State<LessonCard> {
  bool _busy = false;

  Future<void> _rate(int n) async {
    final m = widget.mark;
    if (m == null || _busy) return;
    setState(() => _busy = true);
    try {
      await context.read<OeApi>().rateLesson(m.lessonId, widget.studentId, n);
      setState(() => m.myRating = n);
      if (mounted) toast(context, context.t.rated);
    } catch (e) {
      if (mounted) toastError(context, e);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = context.t;
    final oe = context.oe;
    final l = widget.lesson;
    final m = widget.mark;
    final now = DateTime.now();
    final live = widget.today && !l.cancelled && l.endsAt.isAfter(now);
    Widget? pill;
    if (l.cancelled) {
      pill = Pill(t.cancelled, tone: Tone.red);
    } else if (m != null) {
      final st = switch (m.status) {
        'present' => t.stPresent,
        'late' => t.stLate,
        'absent' => t.stAbsent,
        _ => t.stExcused,
      };
      pill = Pill(m.grade != null ? '$st · ${m.grade}' : st, tone: m.attended ? Tone.ok : (m.status == 'absent' ? Tone.red : Tone.mut));
    } else if (live) {
      pill = Pill(t.today, tone: Tone.info);
    } else if (l.status == 'done') {
      pill = Pill(t.held, tone: Tone.ok);
    }
    final canRate = m != null && m.canRate(now);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
      decoration: BoxDecoration(
        color: oe.surface,
        borderRadius: BorderRadius.circular(OeStyle.cardRadius),
        border: live ? Border.all(color: oe.primary, width: 2) : (OeStyle.ios ? Border.all(color: oe.line) : null),
        boxShadow: OeStyle.ios || live ? null : const [BoxShadow(color: Color(0x0F0F1A33), blurRadius: 2, offset: Offset(0, 1))],
      ),
      child: Opacity(
        opacity: l.cancelled ? .6 : 1,
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [
            Expanded(
              child: Text('${hm(l.startsAt)} – ${hm(l.endsAt)}',
                  style: TextStyle(
                      fontWeight: FontWeight.w600, decoration: l.cancelled ? TextDecoration.lineThrough : null)),
            ),
            ?pill,
          ]),
          const SizedBox(height: 4),
          Text([l.group ?? t.individualLesson, if (l.topic != null) l.topic!].join(' · '),
              style: const TextStyle(fontWeight: FontWeight.w600)),
          if (l.room != null || l.teacher != null) ...[
            const SizedBox(height: 6),
            Wrap(spacing: 12, runSpacing: 4, children: [
              if (l.room != null) _Meta(icon: 'door', text: t.room(l.room!)),
              if (l.teacher != null) _Meta(icon: 'user', text: l.teacher!),
            ]),
          ],
          if (m?.comment != null) ...[
            const SizedBox(height: 8),
            Text('«${m!.comment!}»', style: TextStyle(fontSize: 13, color: oe.ink, fontStyle: FontStyle.italic)),
          ],
          if (canRate || (m?.myRating != null)) ...[
            const SizedBox(height: 6),
            Row(children: [
              Expanded(
                  child: Text(m!.myRating != null ? t.yourRating : t.rateLesson,
                      style: TextStyle(fontSize: 13, color: oe.muted))),
              StarRating(value: m.myRating ?? 0, onRate: canRate && !_busy ? _rate : null),
            ]),
          ],
        ]),
      ),
    );
  }
}

class _Meta extends StatelessWidget {
  const _Meta({required this.icon, required this.text});
  final String icon;
  final String text;

  @override
  Widget build(BuildContext context) => Row(mainAxisSize: MainAxisSize.min, children: [
        OeIcon(icon, size: 16, color: context.oe.muted),
        const SizedBox(width: 4),
        Text(text, style: TextStyle(fontSize: 13, color: context.oe.muted)),
      ]);
}

/// Five stars; tappable when [onRate] is set.
class StarRating extends StatelessWidget {
  const StarRating({super.key, required this.value, this.onRate, this.size = 22});
  final int value;
  final ValueChanged<int>? onRate;
  final double size;

  @override
  Widget build(BuildContext context) {
    final oe = context.oe;
    return Semantics(
      label: context.t.starsN(value),
      child: Row(mainAxisSize: MainAxisSize.min, children: [
        for (var i = 1; i <= 5; i++)
          GestureDetector(
            key: Key('star-$i'),
            onTap: onRate == null ? null : () => onRate!(i),
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 2, vertical: 4),
              child: OeIcon('star', size: size, color: oe.warn, duo: i <= value ? 1 : 0),
            ),
          ),
      ]),
    );
  }
}
