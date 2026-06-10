import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../features/scanner/scanner_screen.dart';

final routerProvider = Provider<GoRouter>((ref) {
  return GoRouter(
    initialLocation: '/scanner',
    routes: [
      GoRoute(path: '/scanner', builder: (ctx, state) => const ScannerScreen()),
      // TODO (Codex): Add /dashboard, /invoices, /login routes
    ],
  );
});
