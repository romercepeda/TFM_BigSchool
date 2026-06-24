// Route table — Spec D10 §6.1.

export interface RouteMatch {
  screen: string;
  params: Record<string, string>;
  authRequired: boolean;
}

interface RouteDef {
  pattern: RegExp;
  paramNames: string[];
  screen: string;
  authRequired: boolean;
}

function route(
  template: string,
  screen: string,
  authRequired = true,
): RouteDef {
  const paramNames: string[] = [];
  const regexStr = template
    .replace(/:([^/]+)/g, (_m, name: string) => {
      paramNames.push(name);
      return '([^/]+)';
    })
    .replace(/\//g, '\\/');
  return { pattern: new RegExp(`^${regexStr}$`), paramNames, screen, authRequired };
}

const ROUTES: RouteDef[] = [
  route('/login',                                                               'pi-login-screen',            false),
  route('/portfolios/new',                                                      'pi-create-portfolio-screen'),
  route('/portfolios/:portfolioId/add-asset',                                   'pi-add-asset-screen'),
  route('/portfolios/:portfolioId/assets/:holdingId/levels',                    'pi-set-levels-screen'),
  route('/portfolios/:portfolioId/assets/:holdingId/analysis',                  'pi-analysis-screen'),
  route('/portfolios/:portfolioId/assets/:holdingId/history',                   'pi-history-screen'),
  route('/portfolios/:portfolioId/assets/:holdingId',                           'pi-asset-detail-screen'),
  route('/portfolios/:portfolioId/alerts',                                      'pi-alerts-screen'),
  route('/portfolios/:portfolioId',                                             'pi-dashboard-screen'),
  route('/portfolios',                                                          'pi-portfolios-screen'),
  route('/settings',                                                            'pi-settings-screen'),
];

export function matchRoute(path: string): RouteMatch | null {
  for (const def of ROUTES) {
    const m = path.match(def.pattern);
    if (m) {
      const params: Record<string, string> = {};
      def.paramNames.forEach((name, i) => { params[name] = m[i + 1]; });
      return { screen: def.screen, params, authRequired: def.authRequired };
    }
  }
  return null;
}
