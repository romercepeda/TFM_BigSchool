// Route table — Spec D10 §6.1.

export interface RouteMatch {
  screen: string;
  params: Record<string, string>;
  authRequired: boolean;
  requiredPermission: string | null;
}

interface RouteDef {
  pattern: RegExp;
  paramNames: string[];
  screen: string;
  authRequired: boolean;
  requiredPermission: string | null;
}

function route(
  template: string,
  screen: string,
  authRequired = true,
  requiredPermission: string | null = null,
): RouteDef {
  const paramNames: string[] = [];
  const regexStr = template
    .replace(/:([^/]+)/g, (_m, name: string) => {
      paramNames.push(name);
      return '([^/]+)';
    })
    .replace(/\//g, '\\/');
  return { pattern: new RegExp(`^${regexStr}$`), paramNames, screen, authRequired, requiredPermission };
}

const ROUTES: RouteDef[] = [
  route('/app/login',                                                           'pi-login-screen',             false),
  route('/app/indicators/legend',                                              'pi-indicators-legend-screen'),
  route('/app/portfolios/new',                                                  'pi-create-portfolio-screen'),
  route('/app/portfolios/:portfolioId/add-asset',                               'pi-add-asset-screen'),
  route('/app/portfolios/:portfolioId/assets/:holdingId/levels',                'pi-set-levels-screen'),
  route('/app/portfolios/:portfolioId/assets/:holdingId/analysis',              'pi-analysis-screen'),
  route('/app/portfolios/:portfolioId/assets/:holdingId/history',               'pi-history-screen'),
  route('/app/portfolios/:portfolioId/assets/:holdingId',                       'pi-asset-detail-screen'),
  route('/app/portfolios/:portfolioId/alerts',                                  'pi-alerts-screen'),
  route('/app/portfolios/:portfolioId',                                         'pi-dashboard-screen'),
  route('/app/portfolios',                                                      'pi-portfolios-screen'),
  route('/app/settings',                                                        'pi-settings-screen'),
  route('/app/settings/change-password',                                        'pi-change-password-screen'),
  route('/app/admin/users/:userId',                                             'pi-admin-user-detail-screen', true, 'user.view_any'),
  route('/app/admin/users',                                                     'pi-admin-users-screen',       true, 'user.list'),
  route('/app/admin/roles',                                                     'pi-admin-roles-screen',       true, 'role.list'),
  route('/app/admin/cascade-failures',                                          'pi-admin-cascade-failures-screen', true, 'system.view_audit_log'),
];

export function matchRoute(path: string): RouteMatch | null {
  for (const def of ROUTES) {
    const m = path.match(def.pattern);
    if (m) {
      const params: Record<string, string> = {};
      def.paramNames.forEach((name, i) => { params[name] = m[i + 1]; });
      return {
        screen: def.screen,
        params,
        authRequired: def.authRequired,
        requiredPermission: def.requiredPermission,
      };
    }
  }
  return null;
}
