import sys
N=[1,2,4,8,16]
def paso(v,d,k=5): return N[(N.index(v)+d+k)%5]
def ciclo(k):
    v=8; a=[]
    for _ in range(5): v=paso(v,1,k); a.append(v)
    b=[]
    for _ in range(5): v=paso(v,-1,k); b.append(v)
    return a==[16,1,2,4,8] and b==[4,2,1,16,8]
print("real:",ciclo(5)); print("sabotaje (k=4):",ciclo(4))
