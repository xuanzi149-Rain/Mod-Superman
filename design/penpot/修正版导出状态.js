return Object.entries(storage.revisionRenders||{}).map(([name,r])=>({name,status:r.status,bytes:r.bytes,error:r.error}));
