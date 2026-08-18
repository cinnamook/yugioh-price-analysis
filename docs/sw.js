/* <CYBERSE> service worker — versioned by build timestamp so every publish updates the phone. */
const CACHE='cyberse-20260818130123';
const CORE=['./index.html','./cards.json','./manifest.json','./icons/icon-192.png','./icons/icon-512.png'];
self.addEventListener('install',function(e){self.skipWaiting();e.waitUntil(caches.open(CACHE).then(function(c){return c.addAll(CORE).catch(function(){});}));});
self.addEventListener('activate',function(e){e.waitUntil(caches.keys().then(function(ks){return Promise.all(ks.map(function(k){return k===CACHE?null:caches.delete(k);}));}).then(function(){return self.clients.claim();}));});
self.addEventListener('fetch',function(e){var req=e.request;if(req.method!=='GET')return;
  if(req.mode==='navigate'){e.respondWith(caches.match('./index.html').then(function(h){return h||fetch(req);}));return;}
  if(new URL(req.url).origin!==location.origin)return; /* let card art (CDN) and fonts hit the network */
  /* ignoreSearch: the page requests cards.json?v=<build> for cache-busting, but the
     precache stores it without a query — an exact match would miss and the installed
     app would fail to load its cards with no network. */
  e.respondWith(caches.match(req,{ignoreSearch:true}).then(function(h){return h||fetch(req).then(function(res){var cp=res.clone();caches.open(CACHE).then(function(c){c.put(req,cp);});return res;});}));
});
