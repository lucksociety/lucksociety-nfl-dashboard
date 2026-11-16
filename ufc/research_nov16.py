"""Development-only comparison; Nov 2024+ diagnostic never selects architecture."""
import json
from pathlib import Path
import numpy as np
from scipy.special import expit,logit
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import log_loss
from . import data,features,model
X,bouts,state=features.build(data.history(),data.physical());days=np.array([b['date']for b in bouts]);y=np.array([b['y']for b in bouts]);methods=np.array([b['method']for b in bouts]);context=np.array([b['method_context']for b in bouts]);rounds=np.array([b['rounds']==5 for b in bouts]);oriented=model.strength_inputs(X)*np.where(y,1,-1)[:,None]
train=days<'2023-01-01';cal=(days>='2023-01-01')&(days<'2024-01-01');valid=(days>='2024-01-01')&(days<'2024-11-01');reports={'method':{},'win':{}};losses={}
for kind,z in [('differences',np.column_stack([oriented,rounds])),('context',np.column_stack([oriented,context,rounds]))]:
 m=make_pipeline(StandardScaler(),LogisticRegression(C=.05,max_iter=1500));m.fit(z[train|cal],methods[train|cal]);p=m.predict_proba(z[valid]);classes=list(m[-1].classes_);l=-np.log([p[i,classes.index(k)]for i,k in enumerate(methods[valid])]);reports['method'][kind]=dict(log_loss=float(l.mean()),accuracy=float(np.mean(m.predict(z[valid])==methods[valid])),n=int(valid.sum()));losses[kind]=l
changes=losses['context']-losses['differences'];event=[changes[days[valid]==d].mean()for d in np.unique(days[valid])];reports['method']['paired']=dict(change=float(changes.mean()),event_se=float(np.std(event,ddof=1)/np.sqrt(len(event))),promotion=bool(changes.mean()<-np.std(event,ddof=1)/np.sqrt(len(event))))
# Test a symmetric two-feature logistic calibrator on the 2023 calibration segment only.
for kind in ['logistic','elo']:
 base=model.fit(kind,X[train],y[train]);pc=model.probability(base,X[cal],kind);pv=model.probability(base,X[valid],kind);t=model.temperature(y[cal],pc);temp=expit(logit(np.clip(pv,1e-6,1-1e-6))/t)
 z=lambda p:np.column_stack([logit(np.clip(p,1e-6,1-1e-6)),np.tanh(logit(np.clip(p,1e-6,1-1e-6)))])
 calibrator=LogisticRegression(C=.1,fit_intercept=False).fit(np.vstack([z(pc),-z(pc)]),np.r_[y[cal],1-y[cal]]);new=calibrator.predict_proba(z(pv))[:,1]
 reports['win'][kind]=dict(temperature=t,baseline=model.metrics(y[valid],temp),calibrated=model.metrics(y[valid],new),coefficients=calibrator.coef_.tolist())
Path('out/ufc').mkdir(parents=True,exist_ok=True);Path('out/ufc/development-nov16.json').write_text(json.dumps(reports,indent=2)+'\n');print(json.dumps(reports,indent=2))
