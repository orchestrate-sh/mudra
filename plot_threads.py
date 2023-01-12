import click
import pandas as pd
import datetime
import random
import matplotlib.pyplot as plt
import os

def get_quotient(x, z):
  return z-datetime.datetime.strptime(x, "%Y-%m-%d %H:%M:%S,%f").timestamp()

@click.command()
@click.option('--file', required=True, help='log csv file')
@click.option('--imagename', default='threads.png', help='log csv file')
def cli(file, imagename):
    df = pd.read_csv(f'{os.getcwd()}/{file}')
    df_grouped = df.groupby('log_threading_number').agg(time_min=('time', 'min'),
                          time_max=('time', 'max'),                         
                          actions= ('action', lambda x: x.unique().tolist()),
                          services=('name_service', lambda x: x.unique().tolist()))
    maxmin_time = df_grouped.sort_values('time_min')['time_min'].max()
    maxmax_time = df_grouped.sort_values('time_min')['time_max'].max()
    max_maxtimestamp = datetime.datetime.strptime(maxmin_time, "%Y-%m-%d %H:%M:%S,%f").timestamp()
    max_mintimestamp = datetime.datetime.strptime(maxmax_time, "%Y-%m-%d %H:%M:%S,%f").timestamp()
    df_grouped['time_quotient_max'] = df_grouped['time_max'].apply(lambda x: get_quotient(x,max_maxtimestamp))
    df_grouped['time_quotient_min'] = df_grouped['time_min'].apply(lambda x: get_quotient(x,max_mintimestamp))
    df_grouped['x_position'] = random.sample(range(1, len(df_grouped)+40), len(df_grouped))
    df_grouped['base_text'] = df_grouped[['actions','services']].apply(lambda x: f'{x.name} | {" ".join(x[0])} | {" ".join(x[1])}', axis=1)

    fig, ax = plt.subplots(figsize=(20,20))
    for value, y, log_number in zip(df_grouped['x_position'].tolist(),df_grouped[['time_quotient_max','time_quotient_min']].values.tolist(),df_grouped.index):
        ax.plot([value,value],y, color='purple')
        if y[0]==y[1]:
            ax.scatter(value,y[0], color='crimson')
        plt.text(value,(y[0]+y[1])/2,s=log_number, rotation=90)
    plt.title("Threads vs Timestamp difference")
    plt.xlabel("Threads")
    plt.ylabel("Timestamp difference")
    plt.figtext(0.1,-0.7, '\n'.join(df_grouped['base_text'].tolist()), ha="left", fontsize=14)
    plt.savefig(imagename, bbox_inches = "tight")
    
if __name__ == '__main__':
    cli()
