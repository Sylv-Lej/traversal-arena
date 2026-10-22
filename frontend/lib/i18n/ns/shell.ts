// Textes : cadre du site (navigation, réglages de la page Profil).

const fr = {
  guestNotice: "Compte invité : tes parties ne suivent pas sur un autre appareil.",
  createAccount: "Créer un compte",
  logIn: "Se connecter",
  loggedInAs: "Connecté :",
  logOut: "Se déconnecter",
  nickname: "Pseudo",
  quality: "Qualité 3D",
  qualities: { auto: "Auto", high: "Haute", medium: "Moyenne", low: "Basse" },
  showHeights: "Afficher la hauteur de chaque case",
  sound: "Sons",
  saved: "Enregistré ✓",
};

const en: typeof fr = {
  guestNotice: "Guest account: your games won’t follow you to another device.",
  createAccount: "Create an account",
  logIn: "Log in",
  loggedInAs: "Logged in:",
  logOut: "Log out",
  nickname: "Username",
  quality: "3D quality",
  qualities: { auto: "Auto", high: "High", medium: "Medium", low: "Low" },
  showHeights: "Show each square’s height",
  sound: "Sound",
  saved: "Saved ✓",
};

export default { fr, en };
