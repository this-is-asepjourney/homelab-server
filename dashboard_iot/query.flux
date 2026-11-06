from(bucket: "iot_mqtt")
  |> range(start: -1h)
  |> filter(fn: (r) => r["_measurement"] == "sysctrl")
