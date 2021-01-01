#!/bin/bash

#### config variables
warning_bat_level=25
urgent_bat_level=10
suspend_bat_level=5
battery_name="Battery 0"

#### script
# needed if running in cron
# export $(egrep -z DBUS_SESSION_BUS_ADDRESS /proc/$(pgrep -u $LOGNAME sway | head -1)/environ)
acpi_out=$(acpi -b | pcregrep "$battery_name")
battery_level=$(echo "$acpi_out" | pcregrep -o1 '([0-9]+)\%')
battery_state=$(echo $acpi_out | pcregrep -o1 "$battery_name\: (\S+),")
battery_remaining=$(echo $acpi_out | pcregrep -o1 "[0-9]+\%, (\S+)")

if [ ! -f "/tmp/.battery" ]; then
    echo "$battery_level" > /tmp/.battery
    echo "$battery_state" >> /tmp/.battery
    exit
fi

previous_battery_level=$(cat /tmp/.battery | head -n 1)
previous_battery_state=$(cat /tmp/.battery | tail -n 1)
echo "$battery_level" > /tmp/.battery
echo "$battery_state" >> /tmp/.battery

checkBatteryLevel() {
    if [ $battery_state != "Discharging" ] || [ "${battery_level}" == "${previous_battery_level}" ]; then
        exit
    fi

    if [ $battery_level -le $suspend_bat_level ]; then
        sudo systemctl suspend
    elif [ $battery_level -le $urgent_bat_level ]; then
        notify-send "Low Battery" "Your computer will suspend soon unless plugged into a power outlet." -u critical
    elif [ $battery_level -le $warning_bat_level ]; then
        notify-send "Low Battery" "${battery_level}% (${battery_remaining}) of battery remaining." -u normal
    fi
}

checkBatteryStateChange() {
    if [ "$battery_state" != "Discharging" ] && [ "$previous_battery_state" == "Discharging" ]; then
        notify-send "Charging" "Battery is now plugged in." -u low
    fi

    if [ "$battery_state" == "Discharging" ] && [ "$previous_battery_state" != "Discharging" ]; then
        notify-send "Power Unplugged" "Your computer has been disconnected from power." -u low
    fi
}

checkBatteryStateChange
checkBatteryLevel
