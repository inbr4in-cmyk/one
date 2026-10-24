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
import 'schedule.dart';
import 'shell.dart';

/// Screen 7 — attendance with grades and teacher comments, a 1–5 rating of attended lessons, test results.
class ProgressScreen extends StatelessWidget {
  const ProgressScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final t = context.t;
    final s = context.watch<Session>();
    final c = s.child;
    return Scaffold(
      appBar: NavBar(backLabel: t.navHome, title: s.isParent ? t.progress : t.myProgress, subtitle: s.isParent ? c?.firstName : null),
      body: c == null
          ? const NoChild()
          : Column(children: [
              const ChildSwitcher(),
              Expanded(
                child: Loader<(Attendance, List<TestResult>)>(
                  key: ValueKey('prog-${c.id}'),
                  load: () async {
                    final api = context.read<OeApi>();
                    final r = await Future.wait<Object>([api.attendance(c.id), api.tests(c.id)]);
                    return (r[0] as Attendance, r[1] as List<TestResult>);
                  },
                  builder: (context, d, reload) => _Body(child: c, attendance: d.$1, tests: d.$2, reload: reload),
                ),
              ),
            ]),
    );
  }
}

class _Body extends StatelessWidget {
  const _Body({required this.child, required this.attendance, required this.tests, required this.reload});
  final Child child;
  final Attendance attendance;
  final List<TestResult> tests;
  final Future<void> Function() reload;

  @override
  Widget build(BuildContext context) {
    final t = context.t;
    final oe = context.oe;
    final locale = context.watch<Settings>().locale;
    final graded = attendance.items.where((m) => m.grade != null).take(8).toList().reversed.toList();
    final avg = graded.isEmpty ? null : graded.map((m) => m.grade!).reduce((a, b) => a + b) / graded.length;
    final comment = attendance.items.where((m) => m.comment != null).firstOrNull;
    return PageList(onRefresh: reload, children: [
      OeCard(
        child: Row(children: [
          IconTile('grad', size: 44, radius: 14),
          const SizedBox(width: 12),
          Expanded(
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(t.level, style: TextStyle(fontSize: 13, color: oe.muted)),
              Text(child.level ?? '—', style: display(17, color: oe.brandInk)),
              if (child.mainGroup != null)
                Text([child.mainGroup!.name, child.branch.name].join(' · '), style: TextStyle(fontSize: 13, color: oe.muted)),
            ]),
          ),
          if (child.stars > 0) Pill('★ ${child.stars}', tone: Tone.warn),
        ]),
      ),
      Row(children: [
        Expanded(child: _Kpi(label: t.monthRate, value: attendance.monthRate == null ? '—' : '${attendance.monthRate}%')),
        const SizedBox(width: 8),
        Expanded(child: _Kpi(label: t.monthLessons, value: '${attendance.monthLessons}')),
        const SizedBox(width: 8),
        Expanded(child: _Kpi(label: t.monthPresent, value: '${attendance.monthPresent}')),
      ]),
      if (graded.isNotEmpty)
        OeCard(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Row(children: [
              Expanded(child: Text(t.lessonGrades, style: display(15, color: oe.brandInk))),
              Text.rich(TextSpan(style: TextStyle(fontSize: 13, color: oe.muted), children: [
                TextSpan(text: '${t.average} '),
                TextSpan(text: avg!.toStringAsFixed(1).replaceAll('.', ','), style: TextStyle(color: oe.ink, fontWeight: FontWeight.w700)),
              ])),
            ]),
            const SizedBox(height: 12),
            SizedBox(
              height: 96,
              child: Row(crossAxisAlignment: CrossAxisAlignment.end, children: [
                for (final m in graded)
                  Expanded(
                    child: Column(mainAxisAlignment: MainAxisAlignment.end, children: [
                      Container(
                        constraints: const BoxConstraints(maxWidth: 26),
                        height: 16 + 54 * (m.grade!.clamp(1, 5) / 5),
                        padding: const EdgeInsets.only(top: 3),
                        alignment: Alignment.topCenter,
                        decoration: BoxDecoration(
                          color: m.grade! >= 5 ? oe.primary : oe.navy100,
                          borderRadius: const BorderRadius.vertical(top: Radius.circular(6), bottom: Radius.circular(3)),
                        ),
                        child: Text('${m.grade}',
                            style: TextStyle(
                                fontSize: 12, fontWeight: FontWeight.w700, color: m.grade! >= 5 ? oe.onPrimary : oe.tint)),
                      ),
                      const SizedBox(height: 4),
                      Text('${school(m.at).day}.${school(m.at).month.toString().padLeft(2, '0')}',
                          style: TextStyle(fontSize: 11, color: oe.muted)),
                    ]),
                  ),
              ]),
            ),
          ]),
        ),
      if (tests.isNotEmpty)
        OeList(children: [
          for (final x in tests)
            OeRow(
              title: x.title,
              titleStyle: const TextStyle(fontWeight: FontWeight.w600),
              subtitle: x.finishedAt == null ? null : dayMonth(x.finishedAt!, locale),
              trailing: Row(mainAxisSize: MainAxisSize.min, children: [
                Text('${x.score}/${x.maxScore}', style: display(15, color: oe.ink)),
              ]),
            ),
        ])
      else
        OeCard(child: Text(t.noTests, style: TextStyle(color: oe.muted))),
      if (comment != null)
        OeCard(
          child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Avatar(child.mainGroup?.teacher ?? '·', size: 36, tone: 1),
            const SizedBox(width: 12),
            Expanded(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text(t.teacherComment, style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 13)),
                Text(comment.comment!, style: TextStyle(fontSize: 13, color: oe.muted)),
              ]),
            ),
          ]),
        ),
      SectionTitle(t.attendanceHistory, padding: const EdgeInsets.only(top: 4)),
      if (attendance.items.isEmpty)
        EmptyState(icon: 'cal', title: t.noMarks)
      else
        OeList(children: [for (final m in attendance.items) _MarkRow(mark: m, studentId: child.id)]),
    ]);
  }
}

class _Kpi extends StatelessWidget {
  const _Kpi({required this.label, required this.value});
  final String label;
  final String value;

  @override
  Widget build(BuildContext context) => OeCard(
        padding: const EdgeInsets.all(12),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(label, maxLines: 1, overflow: TextOverflow.ellipsis, style: TextStyle(fontSize: 12, color: context.oe.muted)),
          const SizedBox(height: 4),
          Text(value, style: display(22, color: context.oe.ink)),
        ]),
      );
}

class _MarkRow extends StatefulWidget {
  const _MarkRow({required this.mark, required this.studentId});
  final Mark mark;
  final int studentId;

  @override
  State<_MarkRow> createState() => _MarkRowState();
}

class _MarkRowState extends State<_MarkRow> {
  bool _busy = false;

  Future<void> _rate(int n) async {
    setState(() => _busy = true);
    try {
      await context.read<OeApi>().rateLesson(widget.mark.lessonId, widget.studentId, n);
      setState(() => widget.mark.myRating = n);
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
    final m = widget.mark;
    final locale = context.watch<Settings>().locale;
    final (tone, label) = switch (m.status) {
      'present' => (Tone.ok, t.stPresent),
      'late' => (Tone.warn, t.stLate),
      'absent' => (Tone.red, t.stAbsent),
      _ => (Tone.mut, t.stExcused),
    };
    final canRate = m.canRate(DateTime.now());
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Expanded(
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text('${weekdayShort(m.at, locale)}, ${dayMonth(m.at, locale)} · ${hm(m.at)}',
                  style: const TextStyle(fontWeight: FontWeight.w600)),
              Text(
                  [
                    if (m.group != null) m.group!,
                    if (!m.charged && !m.attended) t.notCharged,
                  ].join(' · '),
                  style: TextStyle(fontSize: 12.5, color: oe.muted)),
            ]),
          ),
          if (m.stars != null && m.stars! > 0) ...[
            OeIcon('star', size: 16, color: oe.warn, duo: 1),
            Text(' ${m.stars}', style: TextStyle(fontSize: 13, color: oe.warn, fontWeight: FontWeight.w600)),
            const SizedBox(width: 8),
          ],
          Pill(m.grade != null ? '$label · ${m.grade}' : label, tone: tone),
        ]),
        if (m.comment != null)
          Padding(padding: const EdgeInsets.only(top: 6), child: Text('«${m.comment}»', style: const TextStyle(fontSize: 13))),
        if (canRate || m.myRating != null)
          Row(children: [
            Expanded(child: Text(m.myRating != null ? t.yourRating : t.rateLesson, style: TextStyle(fontSize: 13, color: oe.muted))),
            StarRating(value: m.myRating ?? 0, onRate: canRate && !_busy ? _rate : null),
          ]),
      ]),
    );
  }
}
