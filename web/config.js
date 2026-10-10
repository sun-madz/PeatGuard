/* PeatGuard settings. Safe to edit.

   googleMapsKey: optional. Leave "" to use the free OpenStreetMap map (no key needed).
     If you add a key, restrict it in Google Cloud Console to your Vercel domain
     (HTTP referrers) and to the "Maps JavaScript API" only.

   feedbackUrl: optional link to a Google Form for user feedback. Leave "" to hide the
     feedback buttons. feedbackZoneParam: the form's pre-fill field id (e.g. "entry.123456789")
     so the area name is filled in automatically; leave "" if you don't need it. */
window.PG_CONFIG = {
  googleMapsKey: "",
  feedbackUrl: "",
  feedbackZoneParam: ""
};
