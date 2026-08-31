-- Export to JSON
local json = require("json")  -- Assuming json library

function exportToJson(data, filename)
  local file = io.open(filename, "w")
  file:write(json.encode(data))
  file:close()
  print("Exported to " .. filename)
end

return { exportToJson = exportToJson }