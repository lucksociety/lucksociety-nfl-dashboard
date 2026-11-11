"""Bind displayed predictions and game identity to the already-frozen snapshot."""
from .model import digest


def verify(report):
    snapshot=report['snapshot']
    if digest(snapshot)!=report['sha256']:raise ValueError('Forecast snapshot hash mismatch')
    if snapshot['requested_date']!=report['date']or snapshot['frozen_at']!=report['frozen_at']:
        raise ValueError('Forecast date/timestamp differs from frozen snapshot')
    predictions={p['id']:p for p in snapshot.get('forecasts',[])}
    inputs={p['game']['id']:p for p in snapshot.get('inputs',[])}
    for row in report['rows']:
        if row['state']!='forecast':continue
        gid=row['game']['id'];original=inputs.get(gid,{})
        if row['prediction']!=predictions.get(gid)or row['game']!=original.get('game')or row.get('availability')!=original.get('availability'):
            raise ValueError('Prediction, game or availability changed after forecast freeze')
