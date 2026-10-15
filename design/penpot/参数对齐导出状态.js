return Object.entries(storage.alignmentRenders||{}).map(([name,r])=>({name,status:r.status,error:r.error}));
