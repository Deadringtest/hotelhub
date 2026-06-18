var CACHE = "hotelhub-v1";
var STATIC = ["/", "/manifest.json"];

self.addEventListener("install", function(e){
  e.waitUntil(caches.open(CACHE).then(function(c){return c.addAll(STATIC);}));
  self.skipWaiting();
});

self.addEventListener("activate", function(e){
  e.waitUntil(caches.keys().then(function(keys){
    return Promise.all(keys.filter(function(k){return k!==CACHE;}).map(function(k){return caches.delete(k);}));
  }));
  self.clients.claim();
});

// Network first - always get fresh data from server
self.addEventListener("fetch", function(e){
  if(e.request.url.indexOf("/api/")>=0){
    // API calls: always network
    e.respondWith(fetch(e.request).catch(function(){
      return new Response(JSON.stringify({error:"Hors ligne"}),{headers:{"Content-Type":"application/json"}});
    }));
  } else {
    // Static files: network first, cache fallback
    e.respondWith(
      fetch(e.request).then(function(r){
        var rc=r.clone();
        caches.open(CACHE).then(function(c){c.put(e.request,rc);});
        return r;
      }).catch(function(){
        return caches.match(e.request);
      })
    );
  }
});
