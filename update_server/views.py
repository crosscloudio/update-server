import datetime
from flask import jsonify, request

import sqlalchemy
import semver
import logging

import pygal
from flask import render_template

from update_server import app, db, model

from calendar import monthrange
from pygal.style import Style

# Py2 compat
try:
    FileNotFoundError
except NameError:
    FileNotFoundError = IOError


custom_style1 = Style(
    # Custom style to differenciate a graph
    colors=('blue', 'red'))



@app.route('/updates/geheime_stats', methods=['GET','POST'])
def stats():
    # Stats related to the CrossCloud's usage
    channel_activity_data = user_activity_per_channel()
    weekly_user_variation = weekly_user_gain_loss()
    weekly_user_count = weekly_users()
    monthly_user_count = monthly_users()
    current_versions_in_use = version_usage()
    return render_template("graphing.html",
                            channel_activity_data=channel_activity_data,
                            weekly_user_variation=weekly_user_variation,
                            weekly_user_count=weekly_user_count,
                            monthly_user_count=monthly_user_count,
                            current_versions_in_use=current_versions_in_use)


def version_usage():
    # Shows the app versions currently in use
    # if a user used several versions during the period this method takes into account (1 week)
    # all of those versions will be counted
    count_start, count_end = version_usage_date_range(request.args.get('date range', 'today'))
    # get the versions used the last week
    version_count = []
    versions = get_filter_list('version', count_start, count_end)
    # for each version used the last week find the user count
    for version in versions:
        version_count.append(len(get_users_between_dates(count_start, count_end,type='version', filter=version)))
    # print the graph, %values
    pie_chart = pygal.Pie()
    pie_chart.title = 'Version usage (in %), from {} users'.format(sum(version_count))
    for version, count in zip(versions, version_count):
        version, = version
        pie_chart.add(version, (count*100)/sum(version_count))
    return pie_chart.render_data_uri()

def version_usage_date_range(range):
    if range in 'today':
        count_end = datetime.date.today()
        count_start = datetime.date.today()
    elif range in 'current week':
        count_end = datetime.date.today()
        count_start = datetime.date.today() - datetime.timedelta(days=datetime.date.today().weekday()) + datetime.timedelta(days=6,weeks=-1)
    elif range in 'current month':
        count_end = datetime.date.today()
        count_start = get_month_list(1)[0][0]
    elif range in 'last month':
        count_end = get_month_list(2)[0][1]
        count_start = get_month_list(2)[0][0]
    elif range in 'last week':
        count_end = (datetime.date.today() - datetime.timedelta(days=datetime.date.today().weekday()) + datetime.timedelta(days=5,weeks=-1))
        count_start = count_end + datetime.timedelta(days=-6)
    return [count_start,count_end]


def weekly_users():
    # unique active users per week
    # Get URL parameters
    number_of_weeks = int(request.args.get('weeks', 4))
    selected_filter = request.args.get('filter', 'version')
    # Create a list with the number of weeks you want to compare
    sunday = (
    datetime.date.today() - datetime.timedelta(days=datetime.date.today().weekday()) + datetime.timedelta(days=6,
                                                                                                          weeks=-1))
    week_list = list(reversed([(sunday - datetime.timedelta(days=(x + 1) * 7),
                                (sunday - datetime.timedelta(days=+1)) - datetime.timedelta(days=(x) * 7)) for x in
                               range(0, number_of_weeks-1)]))
    week_list.append([sunday, datetime.date.today()])
    if selected_filter is not None:
        filter_list = get_filter_list(selected_filter, week_list[0][0], week_list[-1][1])
    users_per_week = []
    for filter in filter_list:
        filter, = filter
        week_data = [filter, []]
        for week in week_list:
            week_data[1].append(len(get_users_between_dates(week[0], week[1], selected_filter, filter)))
        users_per_week.append(week_data)
    line_chart = pygal.StackedBar()
    line_chart.title = 'Weekly unique users count, segmented by {}'.format(selected_filter)
    line_chart.x_labels = [(str(week_list[i][0])+'/'+str(week_list[i][1])) for i in range(0, len(week_list))]
    for week in users_per_week:
        line_chart.add(week[0], week[1])
    return line_chart.render_data_uri()


def monthly_users():
    # unique active users per month
    # Get URL parameters
    number_of_months = int(request.args.get('months', 4))
    selected_filter = request.args.get('filter', 'version')
    # Create a list with the number of months you want to compare
    monthly_users = []
    month_list = get_month_list(number_of_months)
    if selected_filter is not None:
        filter_list = get_filter_list(selected_filter, month_list[0][0], month_list[-1][1])
    # for each month check the user count
    for filter in filter_list:
        filter, = filter
        month_data = [filter, []]
        for month in month_list:
            month_data[1].append(len(get_users_between_dates(month[0], month[1], selected_filter, filter)))
        monthly_users.append(month_data)
    # Create a bar chart
    line_chart =  pygal.StackedBar()
    line_chart.title = 'Monthly unique users count, segmented by {}'.format(selected_filter)
    line_chart.x_labels = [(str(month_list[i][0].year)+'-'+str(month_list[i][0].month)) for i in range(0, len(month_list))]
    for month in monthly_users:
        line_chart.add(month[0], month[1])
    return line_chart.render_data_uri()


def get_month_list(number_of_months):
    # returns a list with the beginning and end dates of the last "number_of_months" months
    month_list = []
    current_month = [datetime.date(datetime.date.today().year, datetime.date.today().month, 1), datetime.date.today()]
    month_list.append([current_month[0], current_month[1]])
    for x in range(1, number_of_months):
        current_month[0] = monthdelta(current_month[0], -1)
        current_month[1] = datetime.date(current_month[0].year, current_month[0].month,
                                 monthrange(current_month[0].year, current_month[0].month)[1])
        month_list.append([current_month[0], current_month[1]])
    return list(reversed(month_list))


def get_filter_list(filter, date_start, date_end):
    # returns a list of all the distinct values in a column
    date_start = datetime.datetime(date_start.year, date_start.month, date_start.day, 0, 0, 0)
    date_end = datetime.datetime(date_end.year, date_end.month, date_end.day, 23, 59, 59)
    if filter in 'channel':
        return db.session.query(sqlalchemy.distinct(model.UpdateRequest.channel)).filter(
            date_start <= model.UpdateRequest.query_time, model.UpdateRequest.query_time <= date_end).all()
    elif filter in 'version':
        return db.session.query(sqlalchemy.distinct(model.UpdateRequest.version)).filter(
            date_start <= model.UpdateRequest.query_time, model.UpdateRequest.query_time <= date_end).filter(
            sqlalchemy.not_(model.UpdateRequest.version.contains('master'))).all()


def monthdelta(date, delta):
    # Return a new date with a X month difference
    m, y = (date.month+delta) % 12, date.year + ((date.month)+delta-1) // 12
    if not m: m = 12
    d = min(date.day, [31,
        29 if y%4==0 and not y%400==0 else 28,31,30,31,30,31,31,30,31,30,31][m-1])
    return date.replace(day=d,month=m, year=y)


def user_activity_per_channel():
    # shows statistics for the number of active users in the last days (by default 30)
    channels = db.session.query(sqlalchemy.distinct(model.UpdateRequest.channel)).all()
    # get URL variables
    number_of_days = int(request.args.get('days', 30))
    # Calculate dateranges  and store dates
    date_list = list(reversed([datetime.date.today() - datetime.timedelta(days=x) for x in range(0, number_of_days)]))
    user_data_matrix = []
    version_data = []
    # fill userdata for all the channels
    for channel in channels:
        channel_data = []
        name, = channel
        for date in date_list:
            channel_data.append(len(get_users_between_dates(date_ini=date, type='channel', filter=channel)))
        user_data_matrix.append([name, channel_data])
    # print the graph
    graph = pygal.Line()
    graph.title = 'User activity for the past {} days, distributed by platform'.format(number_of_days)
    graph.x_labels = date_list
    for platform, user_count in user_data_matrix:
        graph.add(platform, user_count)
    return graph.render_data_uri()


def weekly_user_gain_loss():
    # Track the number of new/lost users by week
    # Get URL parameters
    number_of_weeks = int(request.args.get('weeks', 4))
    # Create a list with the number of weeks you want to compare
    sunday = (datetime.date.today() - datetime.timedelta(days=datetime.date.today().weekday()) + datetime.timedelta(days=6, weeks=-1))
    week_list = list(reversed([(sunday - datetime.timedelta(days=(x+1)*7),
                                (sunday - datetime.timedelta(days=+1)) - datetime.timedelta(days=(x)*7)) for x in range(0, number_of_weeks+1)]))
    previous_week_users = None
    user_gain_list = []
    user_loss_list = []
    # Search the weeks to find the user variations
    for week_start, week_end in week_list:
        current_week_users = set(get_users_between_dates(week_start, week_end))
        if previous_week_users is not None:
            user_gain_list.append(len(current_week_users - previous_week_users))
            user_loss_list.append(len(previous_week_users - current_week_users))
        previous_week_users = current_week_users
    # Print a bar graph
    graph = pygal.Bar()
    graph.title = 'User gain/loss per week (last {} weeks)'.format(number_of_weeks)
    week_list.pop(0)
    graph.x_labels = [(str(week_list[i][0])+'/'+str(week_list[i][1])) for i in range(0, len(week_list))]
    graph.add('Users gained', user_gain_list)
    graph.add('Users lost', user_loss_list)
    return graph.render_data_uri()


def get_users_between_dates(date_ini, date_final=None, type='', filter=None):
    # Gets the number of users from a certain platform that were active during the given date
    # if no arguments are given for the channel it will select the total number of active users
    if(date_final is None):
        date_final = date_ini
    date_early = datetime.datetime(date_ini.year, date_ini.month, date_ini.day, 0, 0, 0)
    date_late = datetime.datetime(date_final.year, date_final.month, date_final.day, 23, 59, 59)
    # select rows between specified dates
    aux = db.session.query(sqlalchemy.distinct(model.UpdateRequest.install_id)).filter(
        date_early <= model.UpdateRequest.query_time, model.UpdateRequest.query_time <= date_late).filter(model.UpdateRequest.install_id != '')
    # add filter for other columns
    if 'channel' in type:
        aux = aux.filter(model.UpdateRequest.channel == filter)
    if 'version' in type:
        aux = aux.filter(model.UpdateRequest.version == filter)
    return aux.all()


@app.route('/updates/<platform>/<version>')
def update(platform, version):
    try:
        ret = get_version_for_channel(version, platform, hostname=request.url_root)
    except FileNotFoundError:
        return '', 404

    if ret:
        return jsonify(ret)
    else:
        return '', 204


def get_version_for_channel(current_version, platform, hostname='https://update.crosscloud.me/'):
    current = semver.parse(current_version)
    channel = current['prerelease']
    if channel is not None and '.' in channel:
        channel, _ = channel.split('.')
    if channel is None:
        channel = "release"
    with open("channels/{}/{}/.versioninfo".format(channel, platform), "r") as vinfofile:
        new_version = vinfofile.read().strip()

    ip = None

    if '.' in request.remote_addr:
        ip = request.remote_addr

    install_id = request.args.get('installId')

    # the upgrade from version 9.1 is critical, it should only be delivered if it has not for the
    # last hour for the same installId
    if current_version == '2016.9.1':
        result = db.session.query(model.UpdateRequest).filter(model.UpdateRequest.install_id == install_id). \
            filter(model.UpdateRequest.query_time > datetime.datetime.utcnow() - datetime.timedelta(hours=1))
        if result.count():
            # if there was a request in the last hour from the same ip ignore it with a 204
            return False

    update_request = model.UpdateRequest(install_id=install_id,
                                         channel=channel,
                                         version=current_version,
                                         platform=platform,
                                         ip=ip)

    db.session.add(update_request)
    db.session.commit()

    if semver.compare(current_version, new_version) == 0:
        return False
    else:
        if platform == "win32_x64":
            filename = "crosscloud-x64-{}.msi".format(new_version)
        elif platform == "darwin_x64":
            filename = "crosscloud-{}-mac.zip".format(new_version)
        else:
            raise FileNotFoundError
        return {'url': "{}{}/{}/{}".format(hostname, channel, platform, filename)}


@app.before_first_request
def setup_logging():
    if not app.debug:
        # In production mode, add log handler to sys.stderr.
        app.logger.addHandler(logging.StreamHandler())
        app.logger.setLevel(logging.INFO)


def test_get_version_for_channel():
    get_version_for_channel('2016.7.1', 'win32_x64')


if __name__ == "__main__":
    test_get_version_for_channel()
