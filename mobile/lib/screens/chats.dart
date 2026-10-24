import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:go_router/go_router.dart';
import 'package:provider/provider.dart';

import '../api/api_client.dart';
import '../api/models.dart';
import '../api/oe_api.dart';
import '../l10n/l10n.dart';
import '../state/counters.dart';
import '../state/realtime.dart';
import '../state/session.dart';
import '../state/settings.dart';
import '../ui/icons.dart';
import '../ui/media.dart';
import '../ui/theme.dart';
import '../ui/widgets.dart';
import '../util/attach.dart';
import '../util/format.dart';

/// Names of the children's teachers, to tag them as «учитель» (the API gives only the sender kind).
Set<String> teacherNames(Session s) => {
      for (final c in s.children)
        for (final g in c.groups)
          if (g.teacher != null) g.teacher!,
    };

String? roleTag(BuildContext context, {required String? kind, String? name, String? position}) {
  if (kind != 'staff') return null;
  final t = context.t;
  if (name != null && teacherNames(context.read<Session>()).contains(name)) return t.roleTeacher;
  final p = position?.toLowerCase() ?? '';
  if (p.contains('учит') || p.contains('teacher') || p.contains('мұғал')) return t.roleTeacher;
  if (p.contains('менедж') || p.contains('manager')) return t.roleManager;
  if (p.contains('админ')) return t.roleAdmin;
  return position?.isNotEmpty == true ? position!.toLowerCase() : t.roleStaff;
}

String listTime(BuildContext context, DateTime at) {
  final a = school(at), n = schoolNow();
  final days = DateTime.utc(n.year, n.month, n.day).difference(DateTime.utc(a.year, a.month, a.day)).inDays;
  if (days == 0) return hm(at);
  if (days == 1) return context.t.yesterday;
  final locale = context.read<Settings>().locale;
  if (days < 7) return weekdayShort(at, locale);
  return dayMonthShort(at, locale);
}

class RoleTag extends StatelessWidget {
  const RoleTag(this.text, {super.key});
  final String text;

  @override
  Widget build(BuildContext context) {
    final oe = context.oe;
    final mgr = text == context.t.roleManager || text == context.t.roleAdmin;
    return Container(
      margin: const EdgeInsets.only(left: 6),
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 1),
      decoration: BoxDecoration(color: mgr ? oe.warn100 : oe.navy100, borderRadius: BorderRadius.circular(6)),
      child: Text(text, style: TextStyle(fontSize: 11, fontWeight: FontWeight.w600, color: mgr ? oe.warn : oe.tint)),
    );
  }
}

// ---------------------------------------------------------------- list (5a / 11a)

class ChatsScreen extends StatefulWidget {
  const ChatsScreen({super.key});

  @override
  State<ChatsScreen> createState() => _ChatsScreenState();
}

class _ChatsScreenState extends State<ChatsScreen> {
  List<Chat>? _chats;
  Object? _error;
  String _q = '';
  StreamSubscription<dynamic>? _rt;
  Timer? _debounce;

  @override
  void initState() {
    super.initState();
    _load();
    _rt = context.read<Realtime>().events.listen((e) {
      if (e['type'] == 'chat.message' || e['type'] == 'realtime.open') {
        _debounce?.cancel();
        _debounce = Timer(const Duration(milliseconds: 400), _load);
      }
    });
  }

  @override
  void dispose() {
    _rt?.cancel();
    _debounce?.cancel();
    super.dispose();
  }

  Future<void> _load() async {
    try {
      final c = await context.read<OeApi>().chats();
      if (mounted) {
        setState(() {
          _chats = c;
          _error = null;
        });
      }
    } catch (e) {
      if (mounted) setState(() => _error = e);
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = context.t;
    final oe = context.oe;
    final s = context.watch<Session>();
    final ios = OeStyle.ios;
    final chats = (_chats ?? const <Chat>[])
        .where((c) => _q.isEmpty || c.title.toLowerCase().contains(_q.toLowerCase()))
        .toList();
    Widget body;
    if (_chats == null && _error == null) {
      body = const Padding(padding: EdgeInsets.all(16), child: Skeleton(lines: 5));
    } else if (_chats == null) {
      body = ErrorState(error: _error!, onRetry: _load);
    } else if (chats.isEmpty) {
      body = ListView(children: [EmptyState(icon: 'chat', title: _q.isEmpty ? t.noChats : t.nothingFound, text: _q.isEmpty ? t.noChatsText : null)]);
    } else {
      body = ListView(
        padding: const EdgeInsets.fromLTRB(16, 0, 16, 96),
        physics: const AlwaysScrollableScrollPhysics(),
        children: _grouped(context, s, chats),
      );
    }
    return Scaffold(
      backgroundColor: Colors.transparent,
      floatingActionButton: ios
          ? null
          : FloatingActionButton.extended(
              key: const Key('new-chat'),
              onPressed: () => context.push('/chats/new'),
              backgroundColor: oe.navy100,
              foregroundColor: oe.brandInk,
              elevation: 2,
              icon: OeIcon('compose', color: oe.brandInk),
              label: Text(t.newChat, style: const TextStyle(fontWeight: FontWeight.w600)),
            ),
      body: Column(children: [
        TabHeader(t.navChats, actions: [
          if (ios) HeaderAction('compose', label: t.newChat, onTap: () => context.push('/chats/new')),
        ]),
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 0, 16, 8),
          child: _SearchField(hint: t.search, onChanged: (v) => setState(() => _q = v)),
        ),
        Expanded(child: RefreshIndicator.adaptive(onRefresh: _load, child: body)),
      ]),
    );
  }

  /// Parents: each chat under the child it is about, so two children's teachers aren't confused (design 11a).
  List<Widget> _grouped(BuildContext context, Session s, List<Chat> chats) {
    Widget row(Chat c) => _ChatRow(chat: c, onTap: () async {
          await context.push('/chats/${c.id}');
          _load();
        });
    if (!s.isParent || s.children.isEmpty) return [for (final c in chats) row(c)];
    final used = <int>{};
    final out = <Widget>[];
    for (final k in s.children) {
      final groupChats = {for (final g in k.groups) if (g.chatId != null) g.chatId!};
      final teacherIds = {for (final g in k.groups) if (g.teacherId != null) g.teacherId!};
      final mine = chats
          .where((c) => !used.contains(c.id) && (groupChats.contains(c.id) || (c.other != null && teacherIds.contains(c.other!.id)) ||
              (c.other != null && c.other!.fullName == k.fullName)))
          .toList();
      if (mine.isEmpty) continue;
      used.addAll(mine.map((c) => c.id));
      out.add(Eyebrow([k.firstName, if (k.mainGroup != null) k.mainGroup!.name].join(' · ')));
      out.addAll(mine.map(row));
    }
    final rest = chats.where((c) => !used.contains(c.id)).toList();
    if (rest.isNotEmpty) {
      out.add(Eyebrow(s.children.length == 1 ? context.t.school : context.t.branchName(s.children.first.branch.name)));
      out.addAll(rest.map(row));
    }
    return out;
  }
}

class _SearchField extends StatelessWidget {
  const _SearchField({required this.hint, required this.onChanged});
  final String hint;
  final ValueChanged<String> onChanged;

  @override
  Widget build(BuildContext context) {
    final oe = context.oe;
    final ios = OeStyle.ios;
    return SizedBox(
      height: ios ? 38 : 52,
      child: TextField(
        onChanged: onChanged,
        textInputAction: TextInputAction.search,
        decoration: InputDecoration(
          hintText: hint,
          filled: true,
          fillColor: ios ? oe.fill : oe.m3nav,
          isDense: true,
          contentPadding: EdgeInsets.zero,
          prefixIcon: Padding(padding: const EdgeInsets.all(10), child: OeIcon('search', size: 18, color: oe.muted)),
          prefixIconConstraints: const BoxConstraints(minWidth: 40),
          border: OutlineInputBorder(borderRadius: BorderRadius.circular(ios ? 12 : 26), borderSide: BorderSide.none),
          enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(ios ? 12 : 26), borderSide: BorderSide.none),
          focusedBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(ios ? 12 : 26), borderSide: BorderSide.none),
        ),
      ),
    );
  }
}

class _ChatRow extends StatelessWidget {
  const _ChatRow({required this.chat, required this.onTap});
  final Chat chat;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final t = context.t;
    final oe = context.oe;
    final c = chat;
    final tag = c.other == null ? null : roleTag(context, kind: c.other!.kind, name: c.other!.fullName, position: c.other!.position);
    final me = context.read<Session>().me?.fullName;
    final last = c.lastText == null
        ? t.noMessages
        : (c.lastSender == null
            ? c.lastText!
            : (c.lastSender == me ? '${t.you}: ${c.lastText}' : (c.isGroup ? '${_short(c.lastSender!)}: ${c.lastText}' : c.lastText!)));
    return InkWell(
      key: Key('chat-${c.id}'),
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 10),
        decoration: OeStyle.ios ? BoxDecoration(border: Border(bottom: BorderSide(color: oe.line))) : null,
        child: Row(children: [
          if (c.isGroup)
            Container(
              width: 44,
              height: 44,
              alignment: Alignment.center,
              decoration: BoxDecoration(color: oe.navy100, shape: BoxShape.circle),
              child: OeIcon('users', size: 22, color: oe.tint),
            )
          else
            Avatar(c.title, size: 44),
          const SizedBox(width: 12),
          Expanded(
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Row(children: [
                Flexible(
                    child: Text(c.title, maxLines: 1, overflow: TextOverflow.ellipsis, style: const TextStyle(fontWeight: FontWeight.w600))),
                if (tag != null) RoleTag(tag),
              ]),
              const SizedBox(height: 2),
              Text(last, maxLines: 1, overflow: TextOverflow.ellipsis, style: TextStyle(fontSize: 14, color: oe.muted)),
            ]),
          ),
          const SizedBox(width: 8),
          Column(crossAxisAlignment: CrossAxisAlignment.end, children: [
            if (c.lastAt != null) Text(listTime(context, c.lastAt!), style: TextStyle(fontSize: 12, color: oe.muted)),
            const SizedBox(height: 6),
            if (c.unread > 0) CountBadge(c.unread) else const SizedBox(height: 22),
          ]),
        ]),
      ),
    );
  }
}

String _short(String name) {
  final p = name.split(' ');
  return p.length > 1 ? '${p[0]} ${p[1].characters.first}.' : name;
}

// ---------------------------------------------------------------- thread (5b / 11b / 15)

class ChatThreadScreen extends StatefulWidget {
  const ChatThreadScreen({super.key, required this.id});
  final int id;

  @override
  State<ChatThreadScreen> createState() => _ChatThreadScreenState();
}

class _ChatThreadScreenState extends State<ChatThreadScreen> {
  final _text = TextEditingController();
  final _scroll = ScrollController();
  final List<ChatMessage> _msgs = [];
  List<ChatMessage> _pinned = [];
  Chat? _chat;
  Object? _error;
  bool _loading = true;
  bool _older = true;
  bool _loadingOlder = false;
  bool _sending = false;
  VoiceRecorder? _rec;
  Timer? _recTick;
  StreamSubscription<dynamic>? _rt;
  late final OeApi _api = context.read<OeApi>();

  @override
  void initState() {
    super.initState();
    _text.addListener(() => setState(() {}));
    _scroll.addListener(() {
      if (_scroll.position.pixels > _scroll.position.maxScrollExtent - 200) _loadOlder();
    });
    _rt = context.read<Realtime>().events.listen(_onEvent);
    _load();
    WidgetsBinding.instance.addPostFrameCallback((_) => _chatRules());
  }

  @override
  void dispose() {
    _rt?.cancel();
    _recTick?.cancel();
    _rec?.cancel();
    _rec?.dispose();
    _text.dispose();
    _scroll.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final r = await Future.wait<Object>([_api.chats(), _api.messages(widget.id), _api.pinned(widget.id)]);
      if (!mounted) return;
      final list = r[0] as List<Chat>;
      setState(() {
        _chat = list.where((c) => c.id == widget.id).firstOrNull;
        _msgs
          ..clear()
          ..addAll(r[1] as List<ChatMessage>);
        _pinned = r[2] as List<ChatMessage>;
        _older = _msgs.length >= 50;
      });
      if (mounted) context.read<Counters>().refresh();
    } catch (e) {
      if (mounted) setState(() => _error = e);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _loadOlder() async {
    if (!_older || _loadingOlder || _msgs.isEmpty) return;
    _loadingOlder = true;
    try {
      final older = await _api.messages(widget.id, beforeId: _msgs.first.id);
      if (!mounted) return;
      setState(() {
        _msgs.insertAll(0, older.where((m) => !_msgs.any((x) => x.id == m.id)));
        _older = older.length >= 50;
      });
    } catch (_) {
    } finally {
      _loadingOlder = false;
    }
  }

  void _add(ChatMessage m) {
    final i = _msgs.indexWhere((x) => x.id == m.id);
    setState(() => i >= 0 ? _msgs[i] = m : _msgs.add(m));
  }

  Future<void> _onEvent(Map<String, dynamic> e) async {
    if (!mounted) return;
    final type = e['type'];
    if (type == 'realtime.open' && _msgs.isNotEmpty) {
      // Reconnected: fetch what was missed.
      try {
        final missed = await _api.messages(widget.id, afterId: _msgs.last.id);
        missed.forEach(_add);
      } catch (_) {}
      return;
    }
    if (e['chat_id'] != widget.id) return;
    if (type == 'chat.message' && e['message'] is Map) {
      _add(ChatMessage.fromJson((e['message'] as Map).cast<String, dynamic>()));
      _api.markRead(widget.id).catchError((_) {});
    } else if (type == 'chat.pinned') {
      final m = ChatMessage.fromJson((e['message'] as Map).cast<String, dynamic>());
      _add(m);
      _pinned = await _api.pinned(widget.id).catchError((_) => _pinned);
      if (mounted) setState(() {});
    } else if (type == 'chat.hidden') {
      final id = e['message_id'];
      setState(() {
        for (final m in _msgs) {
          if (m.id == id) m.hidden = true;
        }
        _pinned.removeWhere((m) => m.id == id);
      });
    }
  }

  Future<void> _chatRules() async {
    final settings = context.read<Settings>();
    if (settings.chatRulesSeen) return;
    settings.chatRulesSeen = true;
    final t = context.t;
    final oe = context.oe;
    await showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      backgroundColor: oe.surface,
      isScrollControlled: true,
      builder: (c) => SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(20, 0, 20, 16),
          child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
            Row(children: [
              IconTile('shield', size: 44, radius: 14),
              const SizedBox(width: 12),
              Text(t.chatRulesTitle, style: display(20, color: oe.brandInk)),
            ]),
            const SizedBox(height: 14),
            for (final (i, s) in [('file', t.chatRule1), ('phone', t.chatRule2), ('flag', t.chatRule3)])
              Padding(
                padding: const EdgeInsets.only(bottom: 10),
                child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  OeIcon(i, size: 20, color: oe.tint),
                  const SizedBox(width: 12),
                  Expanded(child: Text(s, style: const TextStyle(fontSize: 14))),
                ]),
              ),
            const SizedBox(height: 6),
            OeButton(t.understood, onPressed: () => Navigator.pop(c)),
          ]),
        ),
      ),
    );
  }

  bool get _hasPhone => context.read<Session>().isStudent && phonePattern.hasMatch(_text.text);

  Future<void> _sendText() async {
    final text = _text.text.trim();
    if (text.isEmpty || _sending || _hasPhone) return;
    setState(() => _sending = true);
    try {
      final m = await _api.send(widget.id, text: text);
      _text.clear();
      _add(m);
    } catch (e) {
      if (mounted) toastError(context, e);
    } finally {
      if (mounted) setState(() => _sending = false);
    }
  }

  Future<void> _sendFile(Future<Picked?> Function() pick) async {
    Picked? p;
    try {
      p = await pick();
    } catch (e) {
      if (mounted) toastError(context, e);
      return;
    }
    if (p == null || !mounted) return;
    setState(() => _sending = true);
    try {
      final up = await _api.upload(p.bytes, p.name, p.mime);
      final caption = _text.text.trim();
      final m = await _api.send(widget.id,
          fileKey: up.key, fileName: up.name, kind: p.kind, text: p.kind == 'image' && caption.isNotEmpty && !_hasPhone ? caption : null);
      if (p.kind == 'image' && caption.isNotEmpty && !_hasPhone) _text.clear();
      _add(m);
    } catch (e) {
      if (mounted) toastError(context, e);
    } finally {
      if (mounted) setState(() => _sending = false);
    }
  }

  Future<void> _attachMenu() async {
    final t = context.t;
    final r = await pickAction<String>(context, options: [
      ('camera', t.camera, 'camera'),
      ('gallery', t.gallery, 'image'),
      ('file', t.file, 'clip'),
    ]);
    if (r == null) return;
    await _sendFile(r == 'file' ? pickDocument : () => pickPhoto(camera: r == 'camera'));
  }

  Future<void> _startVoice() async {
    final r = VoiceRecorder();
    try {
      if (!await r.start()) {
        await r.dispose();
        if (mounted) toast(context, context.t.micDenied, error: true);
        return;
      }
    } catch (_) {
      if (mounted) toast(context, context.t.micDenied, error: true);
      return;
    }
    HapticFeedback.mediumImpact();
    setState(() => _rec = r);
    _recTick = Timer.periodic(const Duration(milliseconds: 500), (_) => setState(() {}));
  }

  Future<void> _stopVoice({required bool send}) async {
    final r = _rec;
    if (r == null) return;
    _recTick?.cancel();
    setState(() => _rec = null);
    if (!send) {
      await r.cancel();
      await r.dispose();
      return;
    }
    await _sendFile(() async {
      final p = await r.stop();
      await r.dispose();
      return p;
    });
  }

  Future<void> _messageMenu(ChatMessage m) async {
    final t = context.t;
    final mine = m.senderId == context.read<Session>().me?.id;
    final r = await pickAction<String>(context, options: [
      if (m.text != null) ('copy', t.copy, 'copy'),
      if (mine) ('hide', t.hideMessage, 'x'),
      if (!mine) ('report', t.report, 'flag'),
    ], message: mine ? null : t.reportHint);
    if (!mounted || r == null) return;
    if (r == 'copy') {
      await Clipboard.setData(ClipboardData(text: m.text ?? ''));
      if (mounted) toast(context, t.copied);
    } else if (r == 'hide') {
      if (!await confirm(context, title: t.hideTitle, text: t.hideText, ok: t.hideMessage, danger: true)) return;
      try {
        await _api.hideMessage(m.id);
        setState(() => m.hidden = true);
      } catch (e) {
        if (mounted) toastError(context, e);
      }
    } else if (r == 'report') {
      await _report(m);
    }
  }

  /// 15c — a complaint about a message goes to the branch administration with the context; the author isn't told who.
  Future<void> _report(ChatMessage m) async {
    final t = context.t;
    final reason = await pickAction<String>(context, title: t.reportWhy, options: [
      (t.reasonInsult, t.reasonInsult, null),
      (t.reasonSpam, t.reasonSpam, null),
      (t.reasonPersonal, t.reasonPersonal, null),
      (t.reasonOther, t.reasonOther, null),
    ]);
    if (reason == null || !mounted) return;
    try {
      final c = await _api.fileComplaint(
        subject: t.reportSubject(_chat?.title ?? '#${widget.id}'),
        body: t.reportBody(reason, m.senderName ?? '—', '${dmy(m.at)} ${hm(m.at)}', m.text ?? m.fileName ?? t.file, m.id),
        againstUserId: m.senderKind == 'staff' ? m.senderId : null,
      );
      if (mounted) toast(context, t.reportSent(c.dueAt == null ? '' : dmy(c.dueAt!)));
    } catch (e) {
      if (mounted) toastError(context, e);
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = context.t;
    final c = _chat;
    final subtitle = c == null
        ? null
        : (c.isGroup
            ? t.membersN(c.members)
            : roleTag(context, kind: c.other?.kind, name: c.other?.fullName, position: c.other?.position));
    return Scaffold(
      appBar: NavBar(backLabel: t.navChats, title: c?.title ?? t.chat, subtitle: subtitle),
      body: Column(children: [
        NoticeBar(t.chatNotice),
        if (_pinned.isNotEmpty) _PinnedBar(pinned: _pinned),
        Expanded(child: _list(context)),
        _composer(context),
      ]),
    );
  }

  Widget _list(BuildContext context) {
    final t = context.t;
    if (_loading && _msgs.isEmpty) return const Center(child: CircularProgressIndicator.adaptive());
    if (_error != null && _msgs.isEmpty) return ErrorState(error: _error!, onRetry: _load);
    if (_msgs.isEmpty) return EmptyState(icon: 'chat', title: t.noMessages, text: t.firstMessage);
    final me = context.read<Session>().me?.id;
    final group = _chat?.isGroup ?? true;
    final items = <Widget>[];
    for (var i = _msgs.length - 1; i >= 0; i--) {
      final m = _msgs[i];
      final prev = i > 0 ? _msgs[i - 1] : null;
      final out = m.senderId == me;
      final showName = group && !out && (prev == null || prev.senderId != m.senderId);
      items.add(_Bubble(m: m, out: out, showName: showName, group: group, onLongPress: () => _messageMenu(m)));
      if (prev == null || !_sameDay(prev.at, m.at)) items.add(_DaySep(at: m.at));
    }
    return ListView(
      controller: _scroll,
      reverse: true,
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 12),
      children: items,
    );
  }

  Widget _composer(BuildContext context) {
    final t = context.t;
    final oe = context.oe;
    final ios = OeStyle.ios;
    final rec = _rec;
    final hasText = _text.text.trim().isNotEmpty;
    final phone = _hasPhone;
    return Container(
      color: ios ? oe.surface : oe.paper,
      child: SafeArea(
        top: false,
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          // Keys keep the text field (and the keyboard) alive when the warning appears above it.
          if (phone)
            Container(
              key: const ValueKey('phone-warning'),
              margin: const EdgeInsets.fromLTRB(10, 8, 10, 0),
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(color: oe.warn100, borderRadius: BorderRadius.circular(16)),
              child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                OeIcon('alert', color: oe.warn),
                const SizedBox(width: 10),
                Expanded(
                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Text(t.phoneBlockedTitle, style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 14)),
                    Text(t.phoneBlockedText, style: const TextStyle(fontSize: 13)),
                    const SizedBox(height: 8),
                    OeButton(t.removeNumber, small: true, expand: false, onPressed: () {
                      _text.text = _text.text.replaceAll(phonePattern, '').replaceAll(RegExp(r'\s{2,}'), ' ').trim();
                    }),
                  ]),
                ),
              ]),
            ),
          Container(
            key: const ValueKey('composer-bar'),
            decoration: ios ? BoxDecoration(border: Border(top: BorderSide(color: oe.line))) : null,
            padding: const EdgeInsets.fromLTRB(6, 8, 10, 8),
            child: rec != null
                ? Row(children: [
                    IconButton(
                        tooltip: t.cancel, onPressed: () => _stopVoice(send: false), icon: OeIcon('x', color: oe.muted)),
                    Container(width: 10, height: 10, decoration: BoxDecoration(color: oe.red, shape: BoxShape.circle)),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Text(
                          t.recording('${rec.elapsed.inMinutes}:${(rec.elapsed.inSeconds % 60).toString().padLeft(2, '0')}'),
                          style: const TextStyle(fontWeight: FontWeight.w500)),
                    ),
                    _RoundBtn(icon: 'send', label: t.send, onTap: () => _stopVoice(send: true), primary: true),
                  ])
                : Row(children: [
                    IconButton(
                        key: const Key('attach'),
                        tooltip: t.attach,
                        onPressed: _sending ? null : _attachMenu,
                        icon: OeIcon('clip', color: oe.muted)),
                    Expanded(
                      child: TextField(
                        key: const Key('composer'),
                        controller: _text,
                        minLines: 1,
                        maxLines: 5,
                        maxLength: 4000,
                        textCapitalization: TextCapitalization.sentences,
                        decoration: InputDecoration(
                          hintText: t.message,
                          counterText: '',
                          isDense: true,
                          filled: true,
                          fillColor: ios ? oe.paper : oe.m3nav,
                          contentPadding: EdgeInsets.symmetric(horizontal: 14, vertical: ios ? 9 : 13),
                          border: OutlineInputBorder(
                              borderRadius: BorderRadius.circular(ios ? 19 : 24),
                              borderSide: ios ? BorderSide(color: oe.line) : BorderSide.none),
                          enabledBorder: OutlineInputBorder(
                              borderRadius: BorderRadius.circular(ios ? 19 : 24),
                              borderSide: ios ? BorderSide(color: oe.line) : BorderSide.none),
                          focusedBorder: OutlineInputBorder(
                              borderRadius: BorderRadius.circular(ios ? 19 : 24), borderSide: BorderSide(color: oe.tint)),
                        ),
                      ),
                    ),
                    const SizedBox(width: 6),
                    if (!hasText)
                      IconButton(
                          tooltip: t.camera,
                          onPressed: _sending ? null : () => _sendFile(() => pickPhoto(camera: true)),
                          icon: OeIcon('camera', color: oe.muted)),
                    if (_sending)
                      const SizedBox(width: 40, height: 40, child: Padding(padding: EdgeInsets.all(10), child: CircularProgressIndicator(strokeWidth: 2)))
                    else if (hasText)
                      _RoundBtn(key: const Key('send'), icon: 'send', label: t.send, onTap: phone ? null : _sendText, primary: !phone)
                    else
                      _RoundBtn(key: const Key('mic'), icon: 'mic', label: t.recordVoice, onTap: _startVoice, primary: true),
                  ]),
          ),
        ]),
      ),
    );
  }
}

bool _sameDay(DateTime a, DateTime b) {
  final x = school(a), y = school(b);
  return x.year == y.year && x.month == y.month && x.day == y.day;
}

class _RoundBtn extends StatelessWidget {
  const _RoundBtn({super.key, required this.icon, required this.label, required this.onTap, this.primary = false});
  final String icon;
  final String label;
  final VoidCallback? onTap;
  final bool primary;

  @override
  Widget build(BuildContext context) {
    final oe = context.oe;
    return Semantics(
      button: true,
      label: label,
      child: Material(
        color: primary ? oe.primary : oe.fill,
        shape: const CircleBorder(),
        child: InkWell(
          customBorder: const CircleBorder(),
          onTap: onTap,
          child: SizedBox(width: 40, height: 40, child: Center(child: OeIcon(icon, size: 20, color: primary ? oe.onPrimary : oe.muted))),
        ),
      ),
    );
  }
}

class _PinnedBar extends StatelessWidget {
  const _PinnedBar({required this.pinned});
  final List<ChatMessage> pinned;

  @override
  Widget build(BuildContext context) {
    final t = context.t;
    final oe = context.oe;
    final m = pinned.first;
    return InkWell(
      onTap: () => showModalBottomSheet<void>(
        context: context,
        showDragHandle: true,
        backgroundColor: oe.surface,
        builder: (c) => SafeArea(
          child: ListView(shrinkWrap: true, padding: const EdgeInsets.fromLTRB(16, 0, 16, 16), children: [
            Text(t.pinnedN(pinned.length), style: display(16, color: oe.brandInk)),
            const SizedBox(height: 10),
            for (final p in pinned)
              Padding(
                padding: const EdgeInsets.only(bottom: 10),
                child: OeCard(
                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Text('${p.senderName ?? ''} · ${dmy(p.at)} ${hm(p.at)}', style: TextStyle(fontSize: 12, color: oe.muted)),
                    if (p.text != null) SelectableText(p.text!),
                    if (p.fileUrl != null) Padding(padding: const EdgeInsets.only(top: 8), child: Attachment(url: p.fileUrl!, name: p.fileName, kind: p.kind)),
                  ]),
                ),
              ),
          ]),
        ),
      ),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
        decoration: BoxDecoration(color: oe.surface, border: Border(bottom: BorderSide(color: oe.line))),
        child: IntrinsicHeight(
          child: Row(children: [
            Container(width: 3, decoration: BoxDecoration(color: oe.red, borderRadius: BorderRadius.circular(2))),
            const SizedBox(width: 10),
            OeIcon('pushpin', size: 18, color: oe.red),
            const SizedBox(width: 8),
            Expanded(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text(pinned.length > 1 ? t.pinnedN(pinned.length) : t.pinned,
                    style: TextStyle(fontSize: 12, color: oe.red, fontWeight: FontWeight.w600)),
                Text(m.text ?? m.fileName ?? t.file, maxLines: 1, overflow: TextOverflow.ellipsis, style: const TextStyle(fontSize: 13.5)),
              ]),
            ),
            OeIcon('chev-r', size: 20, color: oe.muted),
          ]),
        ),
      ),
    );
  }
}

class _DaySep extends StatelessWidget {
  const _DaySep({required this.at});
  final DateTime at;

  @override
  Widget build(BuildContext context) {
    final oe = context.oe;
    final n = schoolNow();
    final a = school(at);
    final days = DateTime.utc(n.year, n.month, n.day).difference(DateTime.utc(a.year, a.month, a.day)).inDays;
    final label = days == 0 ? context.t.today : (days == 1 ? context.t.yesterday : dayMonth(at, context.read<Settings>().locale));
    return Center(
      child: Container(
        margin: const EdgeInsets.symmetric(vertical: 8),
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 3),
        decoration: BoxDecoration(color: oe.fill, borderRadius: BorderRadius.circular(999)),
        child: Text(label, style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: oe.muted)),
      ),
    );
  }
}

class _Bubble extends StatelessWidget {
  const _Bubble({required this.m, required this.out, required this.showName, required this.group, required this.onLongPress});
  final ChatMessage m;
  final bool group;
  final bool out;
  final bool showName;
  final VoidCallback onLongPress;

  @override
  Widget build(BuildContext context) {
    final t = context.t;
    final oe = context.oe;
    final tag = showName ? roleTag(context, kind: m.senderKind, name: m.senderName) : null;
    final fg = out ? oe.onPrimary : oe.ink;
    final time = Text(hm(m.at), style: TextStyle(fontSize: 11, color: out ? oe.onHero2 : oe.muted));
    Widget content;
    if (m.hidden) {
      content = Text(t.messageHidden, style: TextStyle(fontStyle: FontStyle.italic, color: out ? oe.onHero2 : oe.muted));
    } else {
      content = Column(crossAxisAlignment: CrossAxisAlignment.start, mainAxisSize: MainAxisSize.min, children: [
        if (m.fileUrl != null)
          Padding(
            padding: EdgeInsets.only(bottom: m.text != null ? 6 : 0),
            child: Attachment(url: m.fileUrl!, name: m.fileName, kind: m.kind, onDark: out),
          ),
        if (m.text != null) Text(m.text!, style: TextStyle(fontSize: 15, color: fg, height: 1.35)),
      ]);
    }
    final bubble = Container(
      padding: const EdgeInsets.fromLTRB(12, 8, 12, 6),
      decoration: BoxDecoration(
        color: out ? oe.primary : oe.surface,
        border: out ? null : Border.all(color: oe.line),
        borderRadius: BorderRadius.only(
          topLeft: const Radius.circular(18),
          topRight: const Radius.circular(18),
          bottomLeft: Radius.circular(out ? 18 : 6),
          bottomRight: Radius.circular(out ? 6 : 18),
        ),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, mainAxisSize: MainAxisSize.min, children: [
        if (showName)
          Padding(
            padding: const EdgeInsets.only(bottom: 2),
            child: Text([m.senderName ?? '', ?tag].join(' · '),
                style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: m.senderKind == 'staff' ? oe.tint : oe.info)),
          ),
        content,
        const SizedBox(height: 2),
        Align(
          alignment: Alignment.centerRight,
          widthFactor: 1,
          child: Row(mainAxisSize: MainAxisSize.min, children: [
            if (m.pinned) ...[OeIcon('pushpin', size: 12, color: out ? oe.onHero2 : oe.red), const SizedBox(width: 4)],
            time,
            if (out) ...[const SizedBox(width: 3), OeIcon('check', size: 13, color: oe.onHero2, strokeWidth: 2)],
          ]),
        ),
      ]),
    );
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Row(
        mainAxisAlignment: out ? MainAxisAlignment.end : MainAxisAlignment.start,
        crossAxisAlignment: CrossAxisAlignment.end,
        children: [
          if (!out) ...[
            showName || !group
                ? Avatar(m.senderName ?? '·', size: 32)
                : const SizedBox(width: 32),
            const SizedBox(width: 8),
          ],
          Flexible(
            child: ConstrainedBox(
              constraints: BoxConstraints(maxWidth: MediaQuery.sizeOf(context).width * .78),
              child: GestureDetector(onLongPress: onLongPress, child: Semantics(label: m.senderName, child: bubble)),
            ),
          ),
        ],
      ),
    );
  }
}

// ---------------------------------------------------------------- new chat

/// Contacts the server allows (teachers, branch staff, parent ↔ own child). A refusal shows the server's reason.
class NewChatScreen extends StatefulWidget {
  const NewChatScreen({super.key});

  @override
  State<NewChatScreen> createState() => _NewChatScreenState();
}

class _NewChatScreenState extends State<NewChatScreen> {
  String _q = '';
  int? _opening;

  Future<void> _open(ChatUser u) async {
    setState(() => _opening = u.id);
    try {
      final c = await context.read<OeApi>().openDirect(u.id);
      if (mounted) context.pushReplacement('/chats/${c.id}');
    } on ApiException catch (e) {
      if (mounted) toast(context, e.detail.isNotEmpty ? e.detail : errorText(context, e), error: true);
    } catch (e) {
      if (mounted) toastError(context, e);
    } finally {
      if (mounted) setState(() => _opening = null);
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = context.t;
    final oe = context.oe;
    return Scaffold(
      appBar: NavBar(backLabel: t.navChats, title: t.newChat),
      body: Column(children: [
        Padding(padding: const EdgeInsets.fromLTRB(16, 4, 16, 8), child: _SearchField(hint: t.searchPeople, onChanged: (v) => setState(() => _q = v))),
        Expanded(
          child: Loader<List<ChatUser>>(
            load: () => context.read<OeApi>().contacts(),
            builder: (context, all, reload) {
              final list = all.where((u) => _q.isEmpty || u.fullName.toLowerCase().contains(_q.toLowerCase())).toList();
              if (list.isEmpty) return EmptyState(icon: 'users', title: _q.isEmpty ? t.noContacts : t.nothingFound);
              return PageList(onRefresh: reload, children: [
                Text(t.contactsHint, style: TextStyle(fontSize: 13, color: oe.muted)),
                OeList(children: [
                  for (final u in list)
                    OeRow(
                      key: Key('contact-${u.id}'),
                      leading: Avatar(u.fullName, size: 40),
                      title: u.fullName,
                      titleStyle: const TextStyle(fontWeight: FontWeight.w600),
                      subtitle: u.subtitle ?? u.position,
                      trailing: _opening == u.id ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2)) : null,
                      chevron: _opening != u.id,
                      onTap: _opening == null ? () => _open(u) : null,
                    ),
                ]),
              ]);
            },
          ),
        ),
      ]),
    );
  }
}
