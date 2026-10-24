/// Maps a server link (notification `link`, push `data.link`) onto an app route.
///
/// Links are written for the web (`/portal/coins`, `/chats/12`, `/chats?chat=12`, `/complaints/5`,
/// `/portal/children/3` …); anything unknown opens the home screen.
String mapServerLink(String? link) {
  if (link == null || link.trim().isEmpty) return '/home';
  final Uri u;
  try {
    u = Uri.parse(link.trim());
  } catch (_) {
    return '/home';
  }
  var path = u.path;
  if (path.length > 1 && path.endsWith('/')) path = path.substring(0, path.length - 1);
  final seg = path.split('/').where((s) => s.isNotEmpty).toList();
  if (seg.isNotEmpty && seg.first == 'portal') seg.removeAt(0);
  if (seg.isEmpty) return '/home';

  int? id(int i) => seg.length > i ? int.tryParse(seg[i]) : null;
  final qChat = int.tryParse(u.queryParameters['chat'] ?? u.queryParameters['id'] ?? '');

  switch (seg.first) {
    case 'chats':
      final c = id(1) ?? qChat;
      return c != null ? '/chats/$c' : '/chats';
    case 'children':
      final c = id(1);
      return c != null ? '/home?child=$c' : '/home';
    case 'coins':
    case 'shop':
      return '/coins';
    case 'payments':
      return '/payments';
    case 'homework':
      final h = id(1);
      return h != null ? '/homework/$h' : '/homework';
    case 'schedule':
    case 'lessons':
      return '/schedule';
    case 'progress':
    case 'attendance':
    case 'tests':
      return '/progress';
    case 'complaints':
    case 'feedback':
      return '/feedback';
    case 'rules':
    case 'consents':
      return '/rules';
    case 'notifications':
      return '/notifications';
    case 'profile':
      return '/profile';
    case 'books':
      return '/books';
    default:
      return '/home';
  }
}
