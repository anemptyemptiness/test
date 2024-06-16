sudo psql -U postgres -d bot -c <<EOF
INSERT INTO employees (user_id, fullname, username, role) VALUES
(292972814, 'Неруссков Дмитрий', '@cryslarecrill', 'admin');
INSERT INTO places (chat_id, title) VALUES
(-4079522582, 'точка 1');
EOF
