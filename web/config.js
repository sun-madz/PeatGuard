/* PeatGuard settings. Safe to edit.

   mapboxToken: Mapbox public token (starts with "pk.") for the map background.
     In your Mapbox account (Tokens page), add URL restrictions for your Vercel address
     so nobody else can use it. Leave "" to use the free CARTO/OpenStreetMap map.
   mapboxStyle: "dark-v11" (default), "satellite-streets-v12", "outdoors-v12" or "light-v11".

   googleMapsKey: optional alternative to Mapbox (only used when mapboxToken is empty).

   feedbackUrl / feedbackZoneParam: optional Google Form for feedback. Leave "" to hide. */
window.PG_CONFIG = {
  mapboxToken: "pk.eyJ1Ijoic3VubWFkeiIsImEiOiJjbXYyOGthZmowZGtyMzRwc3V6YWx0aWtkIn0.xYC2cEvS7FHdAbR59QjTIg",
  mapboxStyle: "dark-v11",
  googleMapsKey: "",
  feedbackUrl: "",
  feedbackZoneParam: ""
};
