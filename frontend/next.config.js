const dev = process.env.NODE_ENV !== "production";

// Tout est servi par ce site : aucune ressource externe (polices auto-hébergées par
// next/font, éclairage 3D généré localement). Next injecte des scripts inline pour
// l'hydratation -> 'unsafe-inline' sur script-src (sinon il faudrait des nonces, donc
// des pages toutes dynamiques). Le dev ajoute eval + websocket (rechargement à chaud).
const CSP = [
  "default-src 'self'",
  `script-src 'self' 'unsafe-inline'${dev ? " 'unsafe-eval'" : ""}`,
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob:",
  "font-src 'self' data:",
  `connect-src 'self'${dev ? " ws: wss:" : ""}`,
  "worker-src 'self' blob:",
  "media-src 'self' data: blob:",
  "object-src 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "frame-ancestors 'none'", // pas d'affichage dans une iframe (anti-clickjacking)
].join("; ");

const SECURITY_HEADERS = [
  { key: "Content-Security-Policy", value: CSP },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "X-Content-Type-Options", value: "nosniff" },
  // Le lien de réinitialisation porte un jeton dans l'URL : jamais envoyé ailleurs.
  { key: "Referrer-Policy", value: "same-origin" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=(), payment=()" },
  { key: "Cross-Origin-Opener-Policy", value: "same-origin" },
  ...(dev ? [] : [{ key: "Strict-Transport-Security", value: "max-age=31536000; includeSubDomains" }]),
];

/** @type {import('next').NextConfig} */
const nextConfig = {
  // Standalone output -> tiny image for Scaleway Serverless Container.
  output: "standalone",
  outputFileTracingRoot: __dirname,
  // Le flux SSE des parties transite par le relais serveur : pas de compression, qui
  // bufferiserait les évènements au lieu de les pousser un par un.
  compress: false,
  reactStrictMode: true,
  poweredByHeader: false,
  async headers() {
    return [{ source: "/:path*", headers: SECURITY_HEADERS }];
  },
};

module.exports = nextConfig;
